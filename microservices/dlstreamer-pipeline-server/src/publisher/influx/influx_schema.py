from marshmallow import Schema, fields, post_dump, EXCLUDE
import json

class DataSchema(Schema):
    height = fields.Int(required=True)
    width = fields.Int(required=True)
    channels = fields.Int(required=True)
    caps = fields.Str(required=True)
    img_format = fields.Str(required=True)
    img_handle = fields.Str(required=True)
    
    objects = fields.List(fields.Raw(), required=False)
    resolution = fields.Dict(required=True)
    pipeline = fields.Dict(required=True)
    gva_meta = fields.List(fields.Raw(), required=False)
    
    encoding_type = fields.Str(required=False)
    encoding_level = fields.Int(required=False)
    frame_id = fields.Int(required=True)
    
    timestamp = fields.Int(load_default=None)
    tags = fields.Dict(load_default={})
    time = fields.Int(required=True)
    S3_meta = fields.Dict(required=False)
    
    class Meta:
        unknown = EXCLUDE  # To ignore unknown fields, the fields not defined in the schema

    @post_dump
    def stringify_complex(self, data, **kwargs):
        for key in ["objects", "resolution", "pipeline", "gva_meta", "tags","S3_meta"]:
            if key in data:
                data[key] = json.dumps(data[key])
        return data