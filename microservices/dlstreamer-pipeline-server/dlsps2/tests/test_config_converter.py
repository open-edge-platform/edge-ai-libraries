# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for config.converter module (element property injection)."""

import pytest

from config.converter import _inject_element_property, build_pipeline_string
from config.models import (
    PipelineConfig, PipelineParameters, PipelineParameterElement,
    PipelineParameterProperty
)


class TestInjectElementProperty:
    """Test _inject_element_property function."""
    
    def test_inject_single_property(self):
        """Test injecting a single property into an element."""
        pipeline = "videotestsrc ! gvadetect name=detector ! fakesink"
        result = _inject_element_property(pipeline, "detector", "model", "/path/to/model.xml")
        
        assert "model=/path/to/model.xml" in result
        assert "name=detector" in result
    
    def test_inject_property_with_path(self):
        """Test injecting property with file path containing special chars."""
        pipeline = "videotestsrc ! gvadetect name=model_elem ! fakesink"
        result = _inject_element_property(pipeline, "model_elem", "model", "/models/resnet50_int8.xml")
        
        assert "model=/models/resnet50_int8.xml" in result
    
    def test_inject_numeric_property(self):
        """Test injecting numeric property value."""
        pipeline = "videotestsrc ! queue name=q ! fakesink"
        result = _inject_element_property(pipeline, "q", "max-size-buffers", 100)
        
        assert "max-size-buffers=100" in result
    
    def test_inject_boolean_property(self):
        """Test injecting boolean property."""
        pipeline = "videotestsrc ! queue name=q ! fakesink"
        result = _inject_element_property(pipeline, "q", "leaky", True)
        
        assert "leaky=True" in result
    
    def test_inject_element_not_found(self):
        """Test that pipeline unchanged when element not found."""
        pipeline = "videotestsrc ! gvadetect name=detector ! fakesink"
        result = _inject_element_property(pipeline, "nonexistent", "model", "/path/to/model")
        
        assert result == pipeline
    
    def test_inject_multiple_properties_same_element(self):
        """Test injecting multiple properties into the same element."""
        pipeline = "videotestsrc ! gvadetect name=detector ! fakesink"
        result = _inject_element_property(pipeline, "detector", "model", "/model1.xml")
        result = _inject_element_property(result, "detector", "device", "CPU")
        
        assert "model=/model1.xml" in result
        assert "device=CPU" in result
    
    def test_inject_preserves_pipeline_structure(self):
        """Test that injection preserves the overall pipeline structure."""
        pipeline = "videotestsrc pattern=snow ! videoconvert ! gvadetect name=det ! videoscale ! fakesink"
        result = _inject_element_property(pipeline, "det", "threshold", 0.5)
        
        # Check key elements still present
        assert "videotestsrc" in result
        assert "videoconvert" in result
        assert "gvadetect" in result
        assert "threshold=0.5" in result
        assert "!" in result  # chain still intact
    
    def test_inject_with_existing_properties(self):
        """Test injection into element that already has properties."""
        pipeline = "videotestsrc ! gvadetect name=detector batch-size=4 ! fakesink"
        result = _inject_element_property(pipeline, "detector", "model", "model.xml")
        
        assert "batch-size=4" in result
        assert "model=model.xml" in result
    
    def test_inject_with_whitespace_variations(self):
        """Test injection handles whitespace variations correctly."""
        pipeline = "videotestsrc   !   gvadetect name=detector   !   fakesink"
        result = _inject_element_property(pipeline, "detector", "device", "GPU")
        
        assert "device=GPU" in result
        assert "gvadetect" in result
    
    def test_inject_with_multiline_pipeline(self):
        """Test injection works with multiline pipeline string."""
        pipeline = """
            videotestsrc !
            gvadetect name=detector !
            fakesink
        """
        result = _inject_element_property(pipeline, "detector", "model", "path/to/model")
        
        assert "model=path/to/model" in result
    
    def test_inject_element_at_start(self):
        """Test injection into first element in pipeline."""
        pipeline = "videotestsrc name=source ! fakesink"
        result = _inject_element_property(pipeline, "source", "pattern", "ball")
        
        assert "pattern=ball" in result
    
    def test_inject_element_at_end(self):
        """Test injection into last element in pipeline."""
        pipeline = "videotestsrc ! fakesink name=output"
        result = _inject_element_property(pipeline, "output", "dump", True)
        
        assert "dump=True" in result


class TestBuildPipelineString:
    """Test build_pipeline_string function."""
    
    def test_build_no_parameters(self):
        """Test building pipeline with no parameters."""
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! fakesink"
        )
        result = build_pipeline_string(config)
        assert result == "videotestsrc ! fakesink"
    
    def test_build_with_scalar_parameter(self):
        """Test building pipeline with scalar parameter."""
        params = PipelineParameters(
            properties={
                "device": PipelineParameterProperty(
                    element=PipelineParameterElement(name="detector")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvadetect name=detector ! fakesink",
            parameters=params
        )
        result = build_pipeline_string(config, parameters={"device": "CPU"})
        
        assert "device=CPU" in result
        assert "name=detector" in result
    
    def test_build_with_dict_parameter(self):
        """Test building pipeline with dict parameter."""
        params = PipelineParameters(
            properties={
                "detector_props": PipelineParameterProperty(
                    element=PipelineParameterElement(name="detector")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvadetect name=detector ! fakesink",
            parameters=params
        )
        param_dict = {
            "detector_props": {
                "model": "/path/to/model.xml",
                "device": "GPU"
            }
        }
        result = build_pipeline_string(config, parameters=param_dict)
        
        assert "model=/path/to/model.xml" in result
        assert "device=GPU" in result
    
    def test_build_ignores_unknown_parameters(self):
        """Test that unknown parameters are ignored silently."""
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! fakesink"
        )
        result = build_pipeline_string(config, parameters={"unknown": "value"})
        
        # Should be unchanged since no parameters defined in config
        assert result == "videotestsrc ! fakesink"
    
    def test_build_multiple_elements_same_parameter_dict(self):
        """Test dict parameter format with multiple properties."""
        params = PipelineParameters(
            properties={
                "inference": PipelineParameterProperty(
                    element=PipelineParameterElement(name="gva_inf")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvadetect name=gva_inf ! fakesink",
            parameters=params
        )
        param_dict = {
            "inference": {
                "model": "/models/detector.xml",
                "device": "HETERO:GPU,CPU",
                "batch-size": 4
            }
        }
        result = build_pipeline_string(config, parameters=param_dict)
        
        assert "model=/models/detector.xml" in result
        assert "device=HETERO:GPU,CPU" in result
        assert "batch-size=4" in result
    
    def test_build_partial_parameter_substitution(self):
        """Test when only some parameters are provided at runtime."""
        params = PipelineParameters(
            properties={
                "model": PipelineParameterProperty(
                    element=PipelineParameterElement(name="detector")
                ),
                "device": PipelineParameterProperty(
                    element=PipelineParameterElement(name="detector")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvadetect name=detector ! fakesink",
            parameters=params
        )
        # Only provide device parameter, not model
        result = build_pipeline_string(config, parameters={"device": "CPU"})
        
        assert "device=CPU" in result
        assert "model=" not in result  # Not injected
    
    def test_build_element_not_in_pipeline(self):
        """Test behavior when parameter element is not in pipeline."""
        params = PipelineParameters(
            properties={
                "model": PipelineParameterProperty(
                    element=PipelineParameterElement(name="missing_element")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! fakesink",
            parameters=params
        )
        result = build_pipeline_string(config, parameters={"model": "model.xml"})
        
        # Pipeline unchanged since element doesn't exist
        assert result == "videotestsrc ! fakesink"
    
    def test_build_none_parameters(self):
        """Test with None parameters argument."""
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! fakesink",
            parameters=None
        )
        result = build_pipeline_string(config, parameters=None)
        
        assert result == "videotestsrc ! fakesink"
    
    def test_build_complex_pipeline(self):
        """Test building complex pipeline with multiple parameters."""
        params = PipelineParameters(
            properties={
                "detector_model": PipelineParameterProperty(
                    element=PipelineParameterElement(name="detector")
                ),
                "classifier_model": PipelineParameterProperty(
                    element=PipelineParameterElement(name="classifier")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline=(
                "videotestsrc ! videoconvert ! "
                "gvadetect name=detector ! queue ! "
                "gvadetect name=classifier ! "
                "fakesink"
            ),
            parameters=params
        )
        params_dict = {
            "detector_model": "/models/detector.xml",
            "classifier_model": "/models/classifier.xml"
        }
        result = build_pipeline_string(config, parameters=params_dict)
        
        assert "detector" in result and "name=detector" in result
        assert "classifier" in result and "name=classifier" in result
        assert "detector_model=/models/detector.xml" in result
        assert "classifier_model=/models/classifier.xml" in result


class TestParameterInjectionCompat:
    """Regression tests for parity with DLSPS 1.0's parameter injection
    (server/gstreamer_pipeline.py, server/schema.py).

    Covers three previously-missing behaviors:
      1. ``element.property`` remaps the request key to a different literal
         GStreamer property name.
      2. ``element`` may be a list, fanning a single parameter out to
         multiple elements.
      3. ``format: "json"`` JSON-encodes the value before injection.
    """

    def test_scalar_parameter_honors_property_remap(self):
        """Request key differs from the actual GStreamer property name."""
        params = PipelineParameters(
            properties={
                "path": PipelineParameterProperty(
                    element=PipelineParameterElement(name="destination", property="file-path")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! filesink name=destination",
            parameters=params,
        )
        result = build_pipeline_string(config, parameters={"path": "/tmp/out.mp4"})

        assert "file-path=/tmp/out.mp4" in result
        assert " path=/tmp/out.mp4" not in result

    def test_scalar_parameter_without_remap_uses_param_name(self):
        """No ``property`` set: falls back to the request key (backward compat)."""
        params = PipelineParameters(
            properties={
                "device": PipelineParameterProperty(
                    element=PipelineParameterElement(name="detector")
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvadetect name=detector ! fakesink",
            parameters=params,
        )
        result = build_pipeline_string(config, parameters={"device": "CPU"})

        assert "device=CPU" in result

    def test_dict_parameter_ignores_property_remap(self):
        """For element-properties dict values, dict keys are already literal
        property names, so ``element.property`` must not be applied."""
        params = PipelineParameters(
            properties={
                "detector_props": PipelineParameterProperty(
                    element=PipelineParameterElement(
                        name="detector", property="should-be-ignored"
                    )
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvadetect name=detector ! fakesink",
            parameters=params,
        )
        result = build_pipeline_string(
            config, parameters={"detector_props": {"model": "/models/detector.xml"}}
        )

        assert "model=/models/detector.xml" in result
        assert "should-be-ignored" not in result

    def test_element_as_list_fans_out_to_multiple_elements(self):
        """A single parameter can target multiple elements at once."""
        params = PipelineParameters(
            properties={
                "device": PipelineParameterProperty(
                    element=[
                        PipelineParameterElement(name="source", property="device"),
                        PipelineParameterElement(name="metaconvert", property="source"),
                    ]
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="v4l2src name=source ! fakesink name=metaconvert",
            parameters=params,
        )
        result = build_pipeline_string(config, parameters={"device": "/dev/video0"})

        assert "name=source device=/dev/video0" in result
        assert "name=metaconvert source=/dev/video0" in result

    def test_json_format_encodes_dict_value(self):
        """``format: json`` JSON-encodes the parameter value before injection."""
        params = PipelineParameters(
            properties={
                "ntp_config": PipelineParameterProperty(
                    element=PipelineParameterElement(
                        name="timesync", property="kwarg", format="json"
                    )
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvapython name=timesync ! fakesink",
            parameters=params,
        )
        result = build_pipeline_string(
            config, parameters={"ntp_config": {"ntpServer": "pool.ntp.org"}}
        )

        assert "kwarg=" in result
        assert '"ntpServer": "pool.ntp.org"' in result

    def test_json_format_encodes_scalar_value(self):
        """``format: json`` also works for scalar (non-dict) values."""
        params = PipelineParameters(
            properties={
                "count": PipelineParameterProperty(
                    element=PipelineParameterElement(
                        name="detector", property="count", format="json"
                    )
                )
            }
        )
        config = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! gvadetect name=detector ! fakesink",
            parameters=params,
        )
        result = build_pipeline_string(config, parameters={"count": 3})

        assert "count=3" in result
