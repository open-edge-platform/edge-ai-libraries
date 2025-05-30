#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import queue
import numpy as np
import cv2
from unittest.mock import MagicMock
import sys
import src.common.log
from gi.repository import Gst
from gstgva.util import gst_buffer_data
from src.server.gstreamer_app_source import GvaFrameData

from src.publisher.publisher import Publisher
from src.publisher.mqtt.mqtt_publisher import MQTTPublisher

from collections import namedtuple
from enum import Enum

# Mock setup for publisher object creation
@pytest.fixture
def setup(mocker):
    app_cfg = {'encoding': {'level': 95, 'type': 'jpeg'},
        'publish_raw_frame': True,
        'pipeline': 'source ! decodebin ! gvatrack ! appsink', 
        'img_handle_length': 10}
    pub_cfg = MagicMock()
    
    mocker.patch('os.getenv', return_value='false')
    mocker.patch('distutils.util.strtobool', return_value=False)
    pub_cfg.get_topics.return_value = ['test1', 'test2']
    mocker.patch('src.publisher.publisher.MQTTPublisher')
    yield app_cfg, pub_cfg

# Publisher object for tests
@pytest.fixture
def pub_obj(setup):
    app_cfg, pub_cfg = setup
    pub_obj = Publisher(app_cfg, pub_cfg, queue.Queue())
    yield pub_obj

class TestPublisher:
    @pytest.mark.parametrize('test_cfg, expected', [
        ({'img_handle_length': 9}, 9), 
        ({'img_handle_length': 0}, ValueError), 
        ({'img_handle_length': -20}, ValueError), 
        ({}, 10)
    ])
    def test_init_img_handle(self, setup, mocker, capfd, test_cfg, expected):
        mock_is_tracking_enabled=mocker.patch('src.publisher.publisher.Publisher._is_tracking_enabled')
        mock_is_tracking_enabled.return_value=True
        app_cfg, pub_cfg = setup
        app_cfg = test_cfg
        
        try:
            pub_obj = Publisher(app_cfg, pub_cfg, queue.Queue())
            pub_obj.img_handle_length = expected
        except Exception as e:
            assert type(e) == expected
            assert 'Invalid string length' in capfd.readouterr().out


    @pytest.mark.parametrize('app_cfg_encoding, expected', [
        ({'encoding': {'level': 95,'type': 'jpeg'}}, True), 
        ({'encoding': {'type': 'jpeg'}}, KeyError), ({}, False)])
    def test_init_encoding(self, setup, app_cfg_encoding, mocker, expected):
        mock_is_tracking_enabled=mocker.patch('src.publisher.publisher.Publisher._is_tracking_enabled')
        mock_is_tracking_enabled.return_value=True
        app_cfg, pub_cfg = setup
        app_cfg = app_cfg_encoding
        try:
            pub_obj = Publisher(app_cfg, pub_cfg, queue.Queue())
            pub_obj.encoding = expected
        except Exception as e:
            assert type(e) == expected

    def test_start(self, mocker, pub_obj):
        mocked_thread = mocker.patch("src.publisher.publisher.th.Thread")
        pub_obj.start()
        assert mocked_thread.called_once_with(target=pub_obj._run)
        assert mocked_thread.return_value.start.call_count == 1

    @pytest.mark.parametrize(
        'is_set, expected',
        [
            (True, False),  #Thread already stopped
            (False, True)  #Thread to be stopped
        ])
    def test_stop(self, mocker, pub_obj, is_set, expected):
        mocked_thread_event = mocker.patch("src.publisher.publisher.th.Event")
        pub_obj.stop_ev = mocked_thread_event
        pub_obj.stop_ev.is_set.return_value = is_set
        
        if not is_set:
            mocked_thread = mocker.patch("src.publisher.publisher.th.Thread")
            pub_obj.start()
        pub_obj.stop()
        assert pub_obj.stop_ev.set.called == expected
        
    
    def test_set_pipeline_info(self, pub_obj):
        # Define test data for pipeline information
        name = "TestPipeline"
        version = "1.0"
        instance_id = "12345"
        get_pipeline_status = MagicMock() 
        pub_obj.set_pipeline_info(name, version, instance_id, get_pipeline_status)
        assert pub_obj.pipeline_name == name, "Pipeline name should be set correctly"
        assert pub_obj.pipeline_version == version, "Pipeline version should be set correctly"
        assert pub_obj.pipeline_instance_id == instance_id, "Pipeline instance ID should be set correctly"
        assert pub_obj.get_pipeline_status == get_pipeline_status, "Get pipeline status function should be set correctly"
    
    
    # @pytest.mark.parametrize(
    #     'mqtt_cfg',
    #     [{"host": "x.x.x.x", "port": 1883}, None
    #     ])
    # def test_get_publishers(self, setup, mqtt_cfg):
    #     app_cfg, pub_cfg = setup
    #     if mqtt_cfg:
    #         app_cfg["mqtt_publisher"] = mqtt_cfg
       
    #     pub_obj = Publisher(app_cfg, pub_cfg, MagicMock())
    #     publishers = pub_obj._get_publishers()
        
    #     if mqtt_cfg:
    #         assert len(publishers) == 1
            
    def test_generate_image_handle(self, pub_obj):
        output = pub_obj._generate_image_handle(9)
        assert isinstance(output, str)
        assert len(output) == 9

    @pytest.mark.parametrize('app_cfg, expected', [
        ({'encoding': {'level': 95,'type': 'jpeg'}}, (True, "jpeg", 95)),
        ({'encoding': {'level': 101,'type': 'jpeg'}}, "Invalid jpeg compression level"),
        ({'encoding': {'level': 0,'type': 'jpeg'}}, (True, "jpeg", 0)),
        ({'encoding': {'level': -1,'type': 'jpeg'}}, "Invalid jpeg compression level"),
        ({'encoding': {'level': 100,'type': 'jpeg'}}, (True,"jpeg", 100)),
        ({'encoding': {'level': 9,'type': 'png'}}, (True, "png", 9)),
        ({'encoding': {'level': 0,'type': 'png'}}, (True, "png", 0)),
        ({'encoding': {'level': -2,'type': 'png'}}, "Invalid png compression level"),
        ({'encoding': {'level': 10,'type': 'png'}}, "Invalid png compression level"),
        ({'encoding': {'level': 5,'type': 'png'}}, (True, "png", 5)),
        ({'encoding': {'level': 95,'type': 'bmp'}}, "Invalid encoding type"),
        ({}, (False, None, None)),
        ({'encoding': {}}, KeyError),
        ({'encoding': {'level': 5}}, KeyError),
        ({'encoding': {'type': 'png'}}, KeyError),
    ])
    def test_enable_encoding(self, caplog, pub_obj, app_cfg, expected):
        pub_obj.app_cfg = app_cfg
        try:
            output = pub_obj._enable_encoding()
            assert output == expected
        except Exception as e:
            if expected == KeyError:
                assert expected == type(e)
            # else:
            #     assert expected in caplog.text

    @pytest.mark.parametrize('app_cfg, expected', [
        ({"pipeline":"element1 name=elem1"}, (None, None)),
        ({"pipeline":"element1 name=elem1 ! jpegenc ! appsink"}, ("jpeg", 85)),
        ({"pipeline":"element1 name=elem1 ! jpegenc name=enc1 quality=90 ! appsink"}, ("jpeg", 90)),
        ({"pipeline":"element1 name=elem1 ! jpegenc name=enc1 quality=90 ! element2 name=elem2 ! jpegenc name=enc2 quality=20 ! appsink"}, ("jpeg", 20)),
        ({"pipeline":"element1 name=elem1 ! jpegenc name=enc1 quality=90 ! element2 name=elem2 ! jpegenc name=enc2 ! appsink"}, ("jpeg", 85)),
        ({"pipeline":"element1 name=elem1 ! pngenc ! appsink"}, ("png", "6")),
        ({"pipeline":"element1 name=elem1 ! pngenc name=enc1 compression-level=8 ! appsink"}, ("png", "8")),
        ({"pipeline":"element1 name=elem1 ! pngenc name=enc1 compression-level=2 ! element2 name=elem2 ! pngenc name=enc2 compression-level=3 ! appsink"}, ("png", "3")),
        ({"pipeline":"element1 name=elem1 ! pngenc name=enc1 compression-level=2 ! element2 name=elem2 ! pngenc name=enc2 ! appsink"}, ("png", "6"))
    ])
    def test_get_pipeline_encoding_properties(self, pub_obj, app_cfg, expected):
        pub_obj.app_cfg = app_cfg

        output = pub_obj._get_pipeline_encoding_properties()
        assert output == expected

    @pytest.mark.parametrize(
        'caps, expected', [("video/x-raw, width=120, height=180", {'height': 180,'width': 120,'channels': 3,'caps': 'video/x-raw, width=(int)120, height=(int)180'}), 
                           ("video/x-raw, width=120", "Failed to get buffer height"),
                           ("video/x-raw, height=180", "Failed to get buffer width")])
    def test_get_gst_buffer_info(self, caplog, mocker, pub_obj, caps, expected):
        mocked_result = MagicMock(spec=Gst.Sample)
        mocked_result.get_caps.return_value = Gst.Caps.from_string(caps)

        mocked_gst_buffer = mocker.patch("src.publisher.publisher.gst_buffer_data")
        mocked_gst_buffer.return_value.__enter__.return_value = b"Test"

        try:
            frame, meta_data = pub_obj._get_gst_buffer_info(mocked_result)
            assert frame == b"Test"
            assert meta_data == {
                'height': 180,
                'width': 120,
                'channels': 3,
                'caps': 'video/x-raw, width=(int)120, height=(int)180'
            }
        except Exception as e:
            if expected == TypeError:
                assert expected == type(e)
            #assert expected in caplog.text

    def test_publish(self, pub_obj, mocker):
        frame = b'sample_frame_data'  
        meta_data = {'info': 'sample_meta_data'}
        mock_datetime = mocker.patch('datetime.datetime')
        pub_obj.add_timestamp = True
        pub_obj.publishers = [MagicMock(), MagicMock()]
        pub_obj.overlayed_frame = b'overlayed_frame_data'
        pub_obj.publishers[0].overlay_annotation = True
        pub_obj.publishers[1].overlay_annotation = False
        pub_obj._publish(frame, meta_data)
        pub_obj.publishers[1].queue.append.assert_called_once_with((frame, meta_data))


    @pytest.mark.parametrize('cfg, frame, meta_data, video_frame',
                             [({'encoding': {'level': 95,'type': 'jpeg'}}, 
                                b'Test', {'height': 120,'width': 90,'channels': 3,'img_handle': 'img00003','caps': 'video/x-raw,'}, 
                                MagicMock()),
                             ({'encoding': {'level': 95,'type': 'jpeg'},'convert_metadata_to_dcaas_format': True}, 
                                b'Test', {'height': 120,'width': 90,'channels': 3,'img_handle': 'img00003','caps': 'video/x-raw,'}, 
                                MagicMock()),
                             ({'encoding': {'level': 95,'type': 'jpeg'}}, 
                                b'Test', {'height': 120,'width': 90,'channels': 3,'caps': 'video/x-raw,'}, 
                                None),
                              ({'encoding': {'level': 95,'type': 'jpeg'}}, 
                                bytes(np.array([[1, 2, 3], [4, 5, 6]])), {'height': 120,'width': 90,'channels': 3,'img_handle': 'img00003','caps': 'image/jpeg,'}, 
                                None),
                              ({'publish_raw_frame': True}, 
                                b'Test', {'height': 120,'width': 90,'channels': 3,'caps': 'video/x-raw,'},
                                None),
                              ({}, 
                                b'Test', {'height': 120,'width': 90,'channels': 3,'caps': 'video/x-raw,'},
                                None)])
    def test_run(self, mocker, setup, cfg, frame, meta_data, video_frame):
        mock_is_tracking_enabled=mocker.patch('src.publisher.publisher.Publisher._is_tracking_enabled')
        mock_is_tracking_enabled.return_value=True
        app_cfg, pub_cfg = setup
        app_cfg = cfg
        pub_obj = Publisher(app_cfg, pub_cfg, MagicMock())
        mocked_event = mocker.patch('src.publisher.publisher.th.Event')
        pub_obj.stop_ev = mocked_event
        pub_obj.stop_ev.is_set.side_effect = [False, True]
        pub_obj.queue.put(queue)
        mocker.patch('src.publisher.publisher.Publisher._get_gst_buffer_info',
                     return_value=(frame, meta_data))
        mocker.patch('src.publisher.publisher.Publisher._publish')
        mocker.patch('src.publisher.publisher.Publisher._add_pipeline_info_metadata')
        mocker.patch('src.publisher.publisher.utils.encode_frame',
                     return_value=[(True, np.array([[1, 2, 3], [4, 5, 6]])),
                                   'jpeg', 95])
        mocker.patch('src.publisher.publisher.Publisher._generate_image_handle',
                     return_value='img00003')

        mocker.patch(
            'src.publisher.publisher.Publisher._get_pipeline_encoding_properties',
            return_value=('jpeg', 95))

        mocker.patch('src.publisher.publisher.Publisher._convert_inference_result')

        if pub_obj.publish_raw_frame:
            expected_frame = b'Test'
        else:
            expected_frame = bytes(np.array([[1, 2, 3], [4, 5, 6]]))
        expected_meta_data = meta_data
        if 'img_handle' not in meta_data.keys():
            expected_meta_data.update({'img_handle': 'img00003'})

        if pub_obj.encoding and not pub_obj.publish_raw_frame:
            expected_meta_data['encoding_type'] = 'jpeg'
            expected_meta_data['encoding_level'] = 95

        if video_frame:
            gva_meta = {'key1': 'value1'}
            mocker.patch('utils.publisher_utils.get_gva_meta_messages',
                         return_value=gva_meta)
            expected_meta_data['gva_meta'] = gva_meta
            mocker.patch('utils.publisher_utils.get_gva_meta_regions',
                         return_value=gva_meta)

        pub_obj._run()

        #pub_obj._publish.assert_called_with(expected_frame, expected_meta_data)

    def test_run_empty_queue(self, mocker, caplog, pub_obj):
        mocked_event = mocker.patch('src.publisher.publisher.th.Event')
        pub_obj.stop_ev = mocked_event
        pub_obj.stop_ev.is_set.side_effect = [False, True]

        pub_obj.queue.get = MagicMock()
        pub_obj.queue.get.side_effect = queue.Empty
        pub_obj._run()
        assert "In publisher thread" not in caplog.text

    def test_run_empty_results(self, mocker, caplog, pub_obj):
        mocked_event = mocker.patch('src.publisher.publisher.th.Event')
        pub_obj.stop_ev = mocked_event
        pub_obj.stop_ev.is_set.side_effect = [False, True]
        pub_obj.queue.get = MagicMock()
        pub_obj.queue.get.return_value = None
        pub_obj._run()

    @pytest.mark.parametrize(
        'exception, expected',
        [(ValueError, 'Value error occured when encoding the image'),
         (cv2.error, 'CV2 error occured when encoding the image'),
         (Exception, 'Error in publisher thread')])
    def test_run_encode_errors(self, mocker, caplog, pub_obj, exception,
                               expected):
        mocked_event = mocker.patch('src.publisher.publisher.th.Event')
        pub_obj.stop_ev = mocked_event
        pub_obj.stop_ev.is_set.side_effect = [False, True]
        pub_obj.queue.put(MagicMock())

        mocker.patch('src.publisher.publisher.Publisher._get_gst_buffer_info',
                     return_value=(b'Test', {
                         'height': 120,
                         'width': 90,
                         'channels': 3,
                         'caps': 'video/x-raw,'
                     }))
        mocker.patch('src.publisher.publisher.utils.encode_frame',
                     side_effect=exception)

        pub_obj._run()

    @pytest.mark.parametrize(
        'exception, expected',
        [(ValueError, 'Value error occured when getting gst buffer data'),
         (Exception, 'Error in publisher thread')])
    def test_run_gst_buffer_error(self, mocker, caplog, pub_obj, exception,
                                  expected):
        mocked_event = mocker.patch('src.publisher.publisher.th.Event')
        pub_obj.stop_ev = mocked_event
        pub_obj.stop_ev.is_set.side_effect = [False, True]
        pub_obj.queue.put(MagicMock())

        mocker.patch('src.publisher.publisher.Publisher._get_gst_buffer_info',
                     side_effect=exception)

        pub_obj._run()
        #assert expected in caplog.text

    class State(Enum):
            QUEUED = 1

    def test_add_pipeline_info_metadata(self, pub_obj):
        pub_obj.pipeline_name = "test"
        pub_obj.pipeline_version = 1
        pub_obj.pipeline_instance_id = 'abc'
        metadata={}
        pub_obj.get_pipeline_status = MagicMock()
        status = {'avg_fps': 19, 'state': TestPublisher.State.QUEUED}
        tuple = namedtuple('PipelineStatus', status)
        pub_obj.get_pipeline_status.return_value = tuple(**status)

        pub_obj._add_pipeline_info_metadata(metadata)

        assert metadata['pipeline'] == {'name': 'test', 'version': 1, 'instance_id': 'abc', 'status': {'avg_fps': 19, 'state': 'QUEUED'}}


    @pytest.mark.parametrize("pipeline, expected", [
        ("source ! decodebin ! gvatrack ! appsink", True),
        ("source ! decodebin ! appsink", False)
    ])
    def test_is_tracking_enabled(self, pub_obj, pipeline, expected):
        """Test that tracking is correctly identified from the pipeline configuration."""
        pub_obj.app_cfg['pipeline'] = pipeline
        assert pub_obj._is_tracking_enabled() == expected
    
    
    @pytest.mark.parametrize("tracking_enabled,meta_data,expected_id", [
        (True, {'annotations': {'objects': [{'bbox': [10, 10, 50, 50]}]}, 'gva_meta': [{'x': 10, 'y': 10, 'width': 40, 'height': 40, 'object_id': 1}]}, 1),
        (False, {'annotations': {'objects': [{'bbox': [10, 10, 50, 50]}]}, 'gva_meta': [{'x': 10, 'y': 10, 'width': 40, 'height': 40, 'object_id': 1}]}, None)
    ])
    def test_add_tracking_info(self, pub_obj, tracking_enabled, meta_data, expected_id):
        """Test adding tracking info based on tracking setting."""
        pub_obj.tracking = tracking_enabled
        updated_meta = pub_obj._add_tracking_info(meta_data)
        object_id = updated_meta['annotations']['objects'][0]['object_id']
        assert object_id == expected_id, f"Expected object ID to be {expected_id} when tracking is {'enabled' if tracking_enabled else 'disabled'}"
    

    def test_convert_inference_result(self, pub_obj):
        metadata = {'gva_meta': [{'x': 457, 'y': 496, 'height': 414, 'width': 167, 'object_id': None, 'tensor': [{'name': 'detection', 'confidence': 0.9830476641654968, 'label_id': 1, 'label':'Person'}]}]}
        expected = ['annotations', 'annotation_type', 'last_modified', 'export_code']
        pub_obj._convert_inference_result(metadata)
        assert list(metadata.keys()) == expected