// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package stream

import (
	"context"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/bluenviron/gortsplib/v5"
	"github.com/bluenviron/gortsplib/v5/pkg/base"
	"github.com/bluenviron/gortsplib/v5/pkg/format"
	"github.com/bluenviron/mediacommon/v2/pkg/codecs/h264"
	"github.com/pion/rtcp"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

func TestRelayDescription(t *testing.T) {
	relay, err := newVideoRelay(&format.H264{PayloadTyp: 96, PacketizationMode: 1}, func() {})
	if err != nil {
		t.Fatal(err)
	}

	defer relay.close()
	if relay.server.WriteQueueSize != relayWriteQueueSize {
		t.Fatalf("unexpected relay write queue size: got %d, want %d", relay.server.WriteQueueSize, relayWriteQueueSize)
	}
	u, err := base.ParseURL(relay.url())
	if err != nil {
		t.Fatal(err)
	}
	if len(relay.path) != 23 || !strings.HasPrefix(relay.path, "/") {
		t.Fatalf("relay path is not shortened: %q", relay.path)
	}
	raw, err := base64.RawURLEncoding.Strict().DecodeString(strings.TrimPrefix(relay.path, "/"))
	if err != nil || len(raw) != 16 {
		t.Fatalf("relay path is not an encoded UUID: %v", err)
	}
	client := &gortsplib.Client{Scheme: u.Scheme, Host: u.Host}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	desc, response, err := client.Describe(u)
	if err != nil {
		t.Fatalf("describe relay: %v; response=%+v", err, response)
	}
	if len(desc.Medias) != 1 {
		t.Fatalf("unexpected relay description: %+v", desc)
	}
}

type fixturePacket struct {
	PTS  int64  `json:"pts"`
	DTS  int64  `json:"dts"`
	Data string `json:"data"`
	au   [][]byte
}

func videoFixture(t *testing.T, codec string) ([]fixturePacket, *videoCodec) {
	t.Helper()
	for _, tool := range []string{"ffmpeg", "ffprobe"} {
		if _, err := exec.LookPath(tool); err != nil {
			t.Skipf("%s is required for media integration tests", tool)
		}
	}
	file := filepath.Join(t.TempDir(), "source.ts")
	args := []string{
		"-v", "error", "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=10",
		"-t", "4", "-c:v", "libx" + codec[1:], "-threads", "1",
		"-g", "10", "-bf", "2", "-sc_threshold", "0",
	}
	var f format.Format = &format.H264{PayloadTyp: 96, PacketizationMode: 1}
	if codec == "h265" {
		args = append(args, "-x265-params", "pools=none:frame-threads=1:log-level=error:open-gop=0:repeat-headers=1")
		f = &format.H265{PayloadTyp: 96}
	}
	args = append(args, "-f", "mpegts", file)
	if output, err := exec.Command("ffmpeg", args...).CombinedOutput(); err != nil {
		t.Fatalf("generate %s fixture: %v\n%s", codec, err, output)
	}
	output, err := exec.Command("ffprobe", "-v", "error", "-select_streams", "v:0",
		"-show_packets", "-show_entries", "packet=pts,dts,data", "-show_data", "-of", "json", file).Output()
	if err != nil {
		t.Fatal(err)
	}
	var probe struct {
		Packets []fixturePacket `json:"packets"`
	}
	if err := json.Unmarshal(output, &probe); err != nil {
		t.Fatal(err)
	}
	adapter, err := newVideoCodec(f)
	if err != nil {
		t.Fatal(err)
	}
	for i := range probe.Packets {
		packet := &probe.Packets[i]
		var raw []byte
		for _, line := range strings.Split(packet.Data, "\n") {
			_, dump, ok := strings.Cut(line, ": ")
			if !ok {
				continue
			}
			hexPart, _, _ := strings.Cut(dump, "  ")
			decoded, err := hex.DecodeString(strings.ReplaceAll(hexPart, " ", ""))
			if err != nil {
				t.Fatal(err)
			}
			raw = append(raw, decoded...)
		}
		var au h264.AnnexB
		if err := au.Unmarshal(raw); err != nil {
			t.Fatal(err)
		}
		packet.au = au
	}
	if len(probe.Packets) != 40 {
		t.Fatalf("expected 40 fixture frames, got %d", len(probe.Packets))
	}
	return probe.Packets, adapter
}

func testPublisher(t *testing.T, codec string, sendNTP bool) (string, time.Time) {
	t.Helper()
	return testPublisherAt(t, codec, sendNTP, time.Date(2026, 2, 3, 4, 5, 6, 0, time.UTC))
}

func testPublisherAt(t *testing.T, codec string, sendNTP bool, baseNTP time.Time) (string, time.Time) {
	t.Helper()
	address, base, _ := testPublisherWithStop(t, codec, sendNTP, baseNTP)
	return address, base
}

func testPublisherWithStop(t *testing.T, codec string, sendNTP bool, baseNTP time.Time) (string, time.Time, func()) {
	t.Helper()
	return testPublisherWithStopAt(t, codec, sendNTP, baseNTP, "127.0.0.1:0")
}

func testPublisherWithStopAt(t *testing.T, codec string, sendNTP bool, baseNTP time.Time, address string) (string, time.Time, func()) {
	t.Helper()
	packets, adapter := videoFixture(t, codec)
	if _, _, err := adapter.prepare(packets[0].au, false); err != nil {
		t.Fatal(err)
	}
	adapter.frozen = true
	relay, err := newVideoRelayAt(adapter.local, func() {}, address)
	if err != nil {
		t.Fatal(err)
	}
	relay.sequenceOrigin = adapter.sequenceOrigin
	relay.timestampOrigin = 0xffff0000
	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup
	wg.Go(func() {
		for !relay.playing.Load() {
			select {
			case <-ctx.Done():
				return
			case <-time.After(5 * time.Millisecond):
			}
		}
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()
		for cycle := int64(0); ; cycle++ {
			for _, packet := range packets {
				select {
				case <-ctx.Done():
					return
				case <-ticker.C:
				}
				pts := packet.PTS - packets[0].PTS + cycle*4*videoClockRate
				au, _, err := adapter.prepare(packet.au, false)
				if err != nil {
					t.Error(err)
					return
				}
				rtpPackets, err := adapter.encode(au)
				if err != nil {
					t.Error(err)
					return
				}
				ntp := baseNTP.Add(ticksDuration(pts))
				for _, p := range rtpPackets {
					p.Timestamp = uint32(0xffff0000 + pts)
					if err := relay.stream.WritePacketRTPWithNTP(relay.media, p, ntp); err != nil {
						t.Error(err)
						return
					}
					if sendNTP {
						stamp := uint64(ntp.Unix()+2208988800)<<32 |
							uint64(ntp.Nanosecond())<<32/1000000000
						err := relay.stream.WritePacketRTCP(relay.media, &rtcp.SenderReport{
							SSRC: p.SSRC, NTPTime: stamp, RTPTime: p.Timestamp,
						})
						if err != nil {
							t.Error(err)
							return
						}
					}
				}
			}
		}
	})
	var once sync.Once
	stop := func() {
		once.Do(func() {
			cancel()
			wg.Wait()
			relay.close()
		})
	}
	t.Cleanup(stop)
	return relay.url(), baseNTP, stop
}

func testService(t *testing.T, length int) *Service {
	t.Helper()
	directory, err := os.MkdirTemp("/dev/shm", "stream-manager-test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.RemoveAll(directory); err != nil {
			t.Error(err)
		}
	})
	service, err := NewService(config.Config{BufferDir: directory, BufferLength: time.Duration(length) * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := service.Close(); err != nil {
			t.Error(err)
		}
	})
	return service
}

func TestRTSPIngest(t *testing.T) {
	if testing.Short() {
		t.Skip("real RTSP/FFmpeg integration")
	}
	for _, codec := range []string{"h264", "h265"} {
		t.Run(codec, func(t *testing.T) {
			source, baseNTP := testPublisher(t, codec, true)
			service := testService(t, 10)
			id, err := service.CreateBuffer(context.Background(), source, "camera", 0)
			if err != nil {
				t.Fatal(err)
			}
			var snapshot model.StreamBuffer
			deadline := time.Now().Add(20 * time.Second)
			for {
				snapshot, err = service.GetStream(context.Background(), id)
				if err != nil {
					t.Fatal(err)
				}
				if snapshot.State == "failed" {
					t.Fatal("ingest failed before producing slices")
				}
				if len(snapshot.Slices) >= 2 {
					break
				}
				if time.Now().After(deadline) {
					t.Fatalf("no usable slices: %+v", snapshot)
				}
				time.Sleep(50 * time.Millisecond)
			}
			if snapshot.SyncConfidence != model.SyncNTPSynced || snapshot.BufferStat.HeldBytes <= 0 {
				t.Fatalf("invalid stream statistics: %+v", snapshot)
			}
			slice := snapshot.Slices[0]
			if slice.SeqNo != 1 || slice.PTSStart != 0 {
				t.Fatalf("first source keyframe was lost: %+v", slice)
			}
			lease, err := service.AcquireBuffer(context.Background(), id, slice.StartTS, slice.EndTS)
			if err != nil {
				t.Fatal(err)
			}
			defer func() {
				if err := lease.Close(); err != nil {
					t.Error(err)
				}
			}()
			reader, err := lease.Next(context.Background())
			if err != nil {
				t.Fatal(err)
			}
			if _, err := io.Copy(io.Discard, reader); err != nil {
				t.Fatal(err)
			}
			delta := slice.StartTS.Sub(baseNTP)
			if delta < 0 || delta > time.Minute || delta%time.Second != 0 {
				t.Fatalf("slice does not carry camera NTP: %+v (delta %s)", slice, delta)
			}
			if slice.EndTS.Sub(slice.StartTS) != time.Second {
				t.Fatalf("not cut at every one-second keyframe: %+v", slice)
			}
			decoded, err := exec.Command("ffmpeg", "-v", "error", "-xerror", "-i", slice.Path,
				"-map", "0:v:0", "-f", "null", "-").CombinedOutput()
			if err != nil {
				t.Fatalf("slice cannot decode independently: %v\n%s", err, decoded)
			}
			probe, err := exec.Command("ffprobe", "-v", "error", "-select_streams", "v:0",
				"-show_entries", "frame=key_frame", "-of", "csv=p=0", slice.Path).Output()
			if err != nil || !strings.HasPrefix(string(probe), "1") {
				t.Fatalf("slice does not start on a keyframe: %v %s", err, probe)
			}
			if len(strings.Fields(string(probe))) != 10 {
				t.Fatalf("first GOP lost or duplicated frames: %s", probe)
			}
			if err := reader.Close(); err != nil {
				t.Fatal(err)
			}
			if err := service.RemoveBuffer(context.Background(), id); !errors.Is(err, ErrActiveReaders) {
				t.Fatalf("active lease did not protect detach: %v", err)
			}
			if err := lease.Close(); err != nil {
				t.Fatal(err)
			}
			if err := service.RemoveBuffer(context.Background(), id); err != nil {
				t.Fatal(err)
			}
			entries, err := os.ReadDir(service.root.Name())
			if err != nil || len(entries) != 0 {
				t.Fatalf("detach left files behind: %v %v", entries, err)
			}
			t.Logf("%s: source-NTP slices [%s,%s), %d bytes", codec, slice.StartTS, slice.EndTS, slice.SizeBytes)
		})
	}
}

func TestRTSPMissingNTP(t *testing.T) {
	if testing.Short() {
		t.Skip("real RTSP/FFmpeg integration")
	}
	source, _ := testPublisher(t, "h264", false)
	buffer := testBuffer(t, 30)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	err := runIngest(ctx, "ffmpeg", source, buffer, func(bool) {}, func() {
		t.Error("published a slice without a source NTP mapping")
	}, time.Second)
	if !errors.Is(err, ErrSourceFailed) || !errors.Is(err, ErrNotNTPSynced) {
		t.Fatalf("missing NTP did not fail: %v", err)
	}
	if len(buffer.snapshot().Slices) != 0 {
		t.Fatal("invented timestamped history without RTCP")
	}
	files, err := os.ReadDir(buffer.root.Name())
	if err != nil || len(files) != 0 {
		t.Fatalf("missing-NTP failure left files: %v %v", files, err)
	}
}

func TestSegmentReportsRejectMismatches(t *testing.T) {
	for _, line := range []string{
		"../S0001.ts,0,1", "S0001.ts,1,2", "S0001.ts,0,2",
		"S0001.ts,NaN,1", "S0001.ts,0,Inf",
	} {
		t.Run(fmt.Sprint(line), func(t *testing.T) {
			buffer := testBuffer(t, 30)
			keys := make(chan keyframeTime, 2)
			keys <- keyframeTime{pts: 0, ntp: time.Unix(100, 0)}
			keys <- keyframeTime{pts: videoClockRate, ntp: time.Unix(101, 0)}
			err := readSegments(context.Background(), strings.NewReader(line+"\n"), keys, buffer, func() {})
			if err == nil || errors.Is(err, io.EOF) {
				t.Fatalf("invalid report was accepted: %v", err)
			}
		})
	}
}
