// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package stream

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/bluenviron/gortsplib/v5"
	"github.com/bluenviron/gortsplib/v5/pkg/base"
	"github.com/bluenviron/gortsplib/v5/pkg/description"
	"github.com/bluenviron/gortsplib/v5/pkg/format"
	"github.com/bluenviron/gortsplib/v5/pkg/format/rtph264"
	"github.com/bluenviron/gortsplib/v5/pkg/format/rtph265"
	"github.com/bluenviron/mediacommon/v2/pkg/codecs/h264"
	"github.com/bluenviron/mediacommon/v2/pkg/codecs/h265"
	"github.com/google/uuid"
	"github.com/pion/rtp"
)

const (
	videoClockRate      = 90000
	maxPendingKeyframes = 256
	sourceClockJump     = time.Second
)

type bestEffortClock struct {
	anchored   bool
	originPTS  int64
	lastPTS    int64
	wrapOffset int64
	originTS   time.Time
}

func (c *bestEffortClock) captureTS(pts int64, anchor time.Time) time.Time {
	if !c.anchored {
		c.anchored, c.originPTS, c.lastPTS, c.originTS = true, pts, pts, anchor.UTC()
		return c.originTS
	}
	if pts < c.lastPTS && c.lastPTS-pts > 1<<32 {
		c.wrapOffset += 1 << 33
	}
	c.lastPTS = pts
	return c.originTS.Add(ticksDuration(pts + c.wrapOffset - c.originPTS))
}

type keyframeTime struct {
	pts        int64
	ntp        time.Time
	receivedAt time.Time
}

type videoCodec struct {
	local          format.Format
	decode         func(*rtp.Packet) ([][]byte, error)
	encode         func([][]byte) ([]*rtp.Packet, error)
	random         func([][]byte) bool
	parameters     [][]byte
	sequenceOrigin uint16
	frozen         bool
}

func newVideoCodec(source format.Format) (*videoCodec, error) {
	switch f := source.(type) {
	case *format.H264:
		decoder, err := f.CreateDecoder()
		if err != nil {
			return nil, err
		}
		sps, pps := bytes.Clone(f.SPS), bytes.Clone(f.PPS)
		local := &format.H264{PayloadTyp: 96, PacketizationMode: 1, SPS: sps, PPS: pps}
		encoder, err := local.CreateEncoder()
		if err != nil {
			return nil, err
		}
		return &videoCodec{
			local: local, decode: decoder.Decode, encode: encoder.Encode,
			random: h264.IsRandomAccess, parameters: [][]byte{sps, pps},
			sequenceOrigin: *encoder.InitialSequenceNumber,
		}, nil
	case *format.H265:
		decoder, err := f.CreateDecoder()
		if err != nil {
			return nil, err
		}
		vps, sps, pps := bytes.Clone(f.VPS), bytes.Clone(f.SPS), bytes.Clone(f.PPS)
		local := &format.H265{PayloadTyp: 96, VPS: vps, SPS: sps, PPS: pps}
		encoder, err := local.CreateEncoder()
		if err != nil {
			return nil, err
		}
		return &videoCodec{
			local: local, decode: decoder.Decode, encode: encoder.Encode,
			random: h265.IsRandomAccess, parameters: [][]byte{vps, sps, pps},
			sequenceOrigin: *encoder.InitialSequenceNumber,
		}, nil
	default:
		return nil, ErrUnsupportedSource
	}
}

func (v *videoCodec) prepare(au [][]byte, started bool) ([][]byte, bool, error) {
	video := false
	filtered := make([][]byte, 0, len(au))
	for _, nalu := range au {
		if len(nalu) == 0 {
			return nil, false, errors.New("empty video NAL unit")
		}
		parameter := -1
		switch v.local.(type) {
		case *format.H264:
			typ := nalu[0] & 0x1f
			if typ == 9 {
				continue
			}
			video = video || (typ >= 1 && typ <= 5)
			if typ == 7 || typ == 8 {
				parameter = int(typ) - 7
			}
		case *format.H265:
			if len(nalu) < 2 {
				return nil, false, errors.New("short H.265 NAL unit")
			}
			typ := (nalu[0] >> 1) & 0x3f
			if typ == 35 {
				continue
			}
			video = video || typ <= 31
			if typ >= 32 && typ <= 34 {
				parameter = int(typ) - 32
			}
		}
		if parameter < 0 {
			filtered = append(filtered, nalu)
			continue
		}
		if (started || v.frozen) && !bytes.Equal(v.parameters[parameter], nalu) {
			return nil, false, errors.New("video parameters changed; reattach the stream")
		}
		v.parameters[parameter] = bytes.Clone(nalu)
	}
	if !video {
		return nil, false, nil
	}
	for _, parameter := range v.parameters {
		if len(parameter) == 0 {
			return nil, false, nil
		}
	}
	if !v.frozen {
		switch f := v.local.(type) {
		case *format.H264:
			f.SPS, f.PPS = v.parameters[0], v.parameters[1]
		case *format.H265:
			f.VPS, f.SPS, f.PPS = v.parameters[0], v.parameters[1], v.parameters[2]
		}
	}
	key := v.random(filtered)
	return filtered, key, nil
}

type rtspInput struct {
	client      *gortsplib.Client
	relay       *videoRelay
	keyframes   chan keyframeTime
	failures    chan error
	failureOnce sync.Once
	failed      atomic.Bool
	bestEffort  atomic.Bool
	stopContext func() bool
	clientDone  chan struct{}
	ready       chan struct{}
}

func (s *rtspInput) fail(reason string) {
	s.failureOnce.Do(func() {
		s.failed.Store(true)
		s.failures <- fmt.Errorf("%w: %s", ErrSourceFailed, reason)
	})
}

func openRTSP(ctx context.Context, sourceURI string, onFrame func(bool), allowBestEffort bool) (_ *rtspInput, result error) {
	u, err := base.ParseURL(sourceURI)
	if err != nil || (u.Scheme != "rtsp" && u.Scheme != "rtsps") || u.User != nil || u.Host == "" {
		return nil, ErrUnsupportedSource
	}
	tcp := gortsplib.ProtocolTCP
	s := &rtspInput{
		client: &gortsplib.Client{
			Scheme: u.Scheme, Host: u.Host, Protocol: &tcp,
			ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Second,
		},
		keyframes: make(chan keyframeTime, maxPendingKeyframes),
		failures:  make(chan error, 1),
		ready:     make(chan struct{}),
	}
	if err := s.client.Start(); err != nil {
		return nil, fmt.Errorf("%w: start RTSP client", ErrSourceFailed)
	}
	s.stopContext = context.AfterFunc(ctx, s.client.Close)
	defer func() {
		if result != nil {
			s.close()
		}
	}()
	desc, _, err := s.client.Describe(u)
	if err != nil {
		return nil, fmt.Errorf("%w: describe RTSP source", ErrSourceFailed)
	}
	var media *description.Media
	for _, candidate := range desc.Medias {
		if candidate.Type == description.MediaTypeVideo {
			if media != nil || len(candidate.Formats) != 1 {
				return nil, ErrUnsupportedSource
			}
			media = candidate
		}
	}
	if media == nil {
		return nil, ErrUnsupportedSource
	}
	sourceFormat := media.Formats[0]
	codec, err := newVideoCodec(sourceFormat)
	if err != nil {
		return nil, ErrUnsupportedSource
	}
	s.relay, err = newVideoRelay(codec.local, func() { s.fail("FFmpeg relay disconnected") })
	if err != nil {
		return nil, err
	}
	s.relay.sequenceOrigin = codec.sequenceOrigin
	if _, err := s.client.Setup(desc.BaseURL, media, 0, 0); err != nil {
		return nil, fmt.Errorf("%w: set up RTSP video", ErrSourceFailed)
	}
	var started bool
	var originPTS int64
	var previousKey keyframeTime
	var ready bool
	var fallbackMode bool
	var fallbackClock bestEffortClock
	s.client.OnPacketsLost = func(_ uint64) {
		onFrame(true)
		s.fail("RTP packets were lost")
	}
	s.client.OnDecodeError = func(_ error) {
		onFrame(true)
		s.fail("invalid RTP or RTCP packet")
	}
	s.client.OnPacketRTP(media, sourceFormat, func(packet *rtp.Packet) {
		if s.failed.Load() || ctx.Err() != nil {
			return
		}
		pts, ptsOK := s.client.PacketPTS(media, packet)
		au, err := codec.decode(packet)
		if errors.Is(err, rtph264.ErrMorePacketsNeeded) || errors.Is(err, rtph265.ErrMorePacketsNeeded) {
			return
		}
		if !started && (errors.Is(err, rtph264.ErrNonStartingPacketAndNoPrevious) ||
			errors.Is(err, rtph265.ErrNonStartingPacketAndNoPrevious)) {
			return
		}
		if err != nil {
			onFrame(true)
			s.fail("cannot assemble a complete video frame")
			return
		}
		au, key, err := codec.prepare(au, started)
		if err != nil {
			onFrame(true)
			s.fail(err.Error())
			return
		}
		if len(au) == 0 {
			return
		}
		ntp, ntpOK := s.client.PacketNTP(media, packet)
		ntpOK = ntpOK && ntp.After(time.Unix(0, 0)) && time.Unix(0, ntp.UnixNano()).Equal(ntp)
		if !ntpOK && !fallbackMode && allowBestEffort && ptsOK {
			fallbackMode = true
			s.bestEffort.Store(true)
		}
		if fallbackMode && ptsOK {
			ntp = fallbackClock.captureTS(pts, time.Now())
			ntpOK = true
		}
		onFrame(!ptsOK || !ntpOK)
		if !ptsOK || !ntpOK {
			if started {
				s.fail("source NTP mapping became unavailable")
			}
			return
		}
		if !s.relay.playing.Load() {
			if key && !ready {
				s.relay.stream.ReloadDesc()
				codec.frozen = true
				ready = true
				close(s.ready)
			}
			return
		}
		if !started {
			if !key {
				return
			}
			originPTS, started = pts, true
		}
		pts -= originPTS
		if pts < previousKey.pts {
			s.fail("open-GOP leading frames cannot form independent slices")
			return
		}
		if key {
			if !previousKey.ntp.IsZero() {
				delta := pts - previousKey.pts
				drift := ntp.Sub(previousKey.ntp) - ticksDuration(delta)
				if delta <= 0 || !ntp.After(previousKey.ntp) || drift > sourceClockJump || drift < -sourceClockJump {
					s.fail("source timestamp discontinuity")
					return
				}
			}
			previousKey = keyframeTime{pts: pts, ntp: ntp.UTC(), receivedAt: time.Now()}
			select {
			case s.keyframes <- previousKey:
			default:
				s.fail("FFmpeg fell behind the bounded keyframe queue")
				return
			}
		}
		packets, err := codec.encode(au)
		if err != nil {
			s.fail("cannot packetize video for FFmpeg")
			return
		}
		for _, p := range packets {
			p.Timestamp = s.relay.timestampOrigin + uint32(pts)
			if err := s.relay.stream.WritePacketRTPWithNTP(s.relay.media, p, ntp); err != nil {
				s.fail("cannot forward video to FFmpeg")
				return
			}
		}
	})
	if _, err := s.client.Play(nil); err != nil {
		return nil, fmt.Errorf("%w: play RTSP source", ErrSourceFailed)
	}
	s.clientDone = make(chan struct{})
	go func() {
		defer close(s.clientDone)
		if err := s.client.Wait(); err != nil && ctx.Err() == nil {
			s.fail("RTSP source disconnected")
		}
	}()
	return s, nil
}

func (s *rtspInput) close() {
	if s.stopContext != nil {
		s.stopContext()
	}
	s.client.Close()
	if s.clientDone != nil {
		<-s.clientDone
	}
	if s.relay != nil {
		s.relay.close()
	}
}

func ticksDuration(ticks int64) time.Duration {
	return time.Duration(ticks/videoClockRate)*time.Second +
		time.Duration(ticks%videoClockRate)*time.Second/videoClockRate
}

type videoRelay struct {
	server          *gortsplib.Server
	stream          *gortsplib.ServerStream
	media           *description.Media
	path            string
	playing         atomic.Bool
	timestampOrigin uint32
	sequenceOrigin  uint16
	mu              sync.Mutex
	session         *gortsplib.ServerSession
	playConn        *gortsplib.ServerConn
	playCSeq        string
	onClosed        func()
}

func newVideoRelay(codec format.Format, onClosed func()) (*videoRelay, error) {
	id, err := uuid.NewRandom()
	if err != nil {
		return nil, err
	}
	r := &videoRelay{
		path: "/" + id.String(), onClosed: onClosed,
		timestampOrigin: binary.BigEndian.Uint32(id[:4]) | 1,
		media:           &description.Media{Type: description.MediaTypeVideo, Formats: []format.Format{codec}},
	}
	r.server = &gortsplib.Server{
		RTSPAddress: "127.0.0.1:0", Handler: r, DisableRTCPSenderReports: true,
		WriteQueueSize: 8192,
	}
	if err := r.server.Start(); err != nil {
		return nil, fmt.Errorf("start local RTSP relay: %w", err)
	}
	r.stream = &gortsplib.ServerStream{
		Server: r.server, Desc: &description.Session{Medias: []*description.Media{r.media}},
	}
	if err := r.stream.Initialize(); err != nil {
		r.server.Close()
		return nil, fmt.Errorf("initialize local RTSP relay: %w", err)
	}
	return r, nil
}

func (r *videoRelay) url() string {
	return "rtsp://" + r.server.NetListener().Addr().String() + r.path
}

func (r *videoRelay) OnDescribe(ctx *gortsplib.ServerHandlerOnDescribeCtx) (*base.Response, *gortsplib.ServerStream, error) {
	if ctx.Path != r.path {
		return &base.Response{StatusCode: base.StatusNotFound}, nil, nil
	}
	return &base.Response{StatusCode: base.StatusOK}, r.stream, nil
}

func (r *videoRelay) OnSetup(ctx *gortsplib.ServerHandlerOnSetupCtx) (*base.Response, *gortsplib.ServerStream, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if ctx.Path != r.path || (r.session != nil && r.session != ctx.Session) {
		return &base.Response{StatusCode: base.StatusNotFound}, nil, nil
	}
	r.session = ctx.Session
	return &base.Response{StatusCode: base.StatusOK}, r.stream, nil
}

func (r *videoRelay) OnPlay(ctx *gortsplib.ServerHandlerOnPlayCtx) (*base.Response, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if ctx.Path != r.path || ctx.Session != r.session {
		return &base.Response{StatusCode: base.StatusNotFound}, nil
	}
	r.playConn = ctx.Conn
	if values := ctx.Request.Header["CSeq"]; len(values) == 1 {
		r.playCSeq = values[0]
	}
	return &base.Response{StatusCode: base.StatusOK}, nil
}

func (r *videoRelay) OnResponse(conn *gortsplib.ServerConn, response *base.Response) {
	r.mu.Lock()
	defer r.mu.Unlock()
	values := response.Header["CSeq"]
	if conn == r.playConn && len(values) == 1 && values[0] == r.playCSeq && response.StatusCode == base.StatusOK {
		// The reader is registered now; advertise the exact first packet rather
		// than a wall-clock-derived RTP origin before releasing the keyframe.
		response.Header["RTP-Info"] = base.HeaderValue{fmt.Sprintf(
			"url=%s/trackID=0;seq=%d;rtptime=%d", r.url(), r.sequenceOrigin, r.timestampOrigin)}
		r.playing.Store(true)
	}
}

func (r *videoRelay) OnSessionClose(ctx *gortsplib.ServerHandlerOnSessionCloseCtx) {
	r.mu.Lock()
	matched := ctx.Session == r.session
	r.mu.Unlock()
	if matched {
		r.onClosed()
	}
}

func (r *videoRelay) close() {
	r.stream.Close()
	r.server.Close()
}
