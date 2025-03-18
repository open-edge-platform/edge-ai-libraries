/*******************************************************************************
 * Copyright (C) 2018-2021 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "callback.h"
#include "manager.h"
#include <iostream>
#include "gva_json_meta.h"

void frame_free(void *obj)
{
}

gboolean init_udfs(GstUDFLoader *udfloader)
{
    gst_gva_json_meta_get_info();
    gst_gva_json_meta_api_get_type();
    try
    {
        cJSON *json = cJSON_Parse(udfloader->config);
        if (json == NULL)
        {
            GST_ELEMENT_ERROR(udfloader, RESOURCE, NOT_FOUND,
                              ("Invalid input for 'config'"),
                              ("Failed to parse JSON string: %s", cJSON_GetErrorPtr()));
            return FALSE;
        }

        udfloader->manager = new Manager(json);
    }
    catch (const std::exception &e)
    {
        GST_ERROR_OBJECT(udfloader, "%s", e.what());
        return false;
    }
    return true;
}

GstFlowReturn process_buffer(GstUDFLoader *udfloader, GstBuffer *buffer)
{
    GstMapInfo map;
    try
    {
        if (!gst_buffer_map(buffer, &map, GST_MAP_READ))
        {
            GST_ELEMENT_ERROR(udfloader, CORE, FAILED, ("Error: "), ("%s", "Invalid buffer"));
            return GST_FLOW_ERROR;
        }

        bool modified = false;

        GstVideoInfo *vid_info = udfloader->info;
        Frame frame((void *)nullptr, frame_free, map.data, vid_info->width, vid_info->height, 3);

        GstGVAJSONMeta *gst_json_meta = GST_GVA_JSON_META_GET(buffer);
        msg_envelope_t *meta = NULL;

        if (gst_json_meta && gst_json_meta->message)
        {
            msg_envelope_serialized_part_t part;
            part.bytes = gst_json_meta->message;
            msg_envelope_serialized_part_t parts[1] = {part};

            msgbus_ret_t ret_t = msgbus_msg_envelope_deserialize(
                CT_JSON, parts, 1, "gst_meta", &meta);

            if (ret_t != MSG_SUCCESS)
            {
                return GST_FLOW_ERROR;
            }
        }
        else
        {
            meta = msgbus_msg_envelope_new(CT_JSON);
        }

        // Previous UDFs might have added img_handle for the
        // frame, do not update the metadata with the regenerated
        // img_handle
        if (!hashmap_get(meta->map, "img_handle"))
        {
            msg_envelope_elem_body_t *img_handle = msgbus_msg_envelope_new_string(
                frame.get_img_handle().c_str());
            msgbus_msg_envelope_put(meta, "img_handle", img_handle);
        }
        // Fetch channel format from the source pad of the udfloader
        // and add it to the metadata
        GstPad *pad = gst_element_get_static_pad(GST_ELEMENT(udfloader), "src");
        GstCaps *caps_format = gst_pad_query_caps(pad, NULL);
        GstStructure *structure = gst_caps_get_structure(caps_format, 0);
        const gchar *img_format = gst_structure_get_string(structure, "format");
        
        msg_envelope_elem_body_t *format = msgbus_msg_envelope_new_string(img_format);
        msgbus_msg_envelope_put(meta, "format", format);

        for (auto handle : *udfloader->manager->get_udf_handlers())
        {
            UdfRetCode ret = handle->process(&frame, meta);

            switch (ret)
            {
            case UdfRetCode::UDF_DROP_FRAME:
                GST_INFO_OBJECT(udfloader, "Dropping frame");
                gst_buffer_unmap(buffer, &map);
                msgbus_msg_envelope_destroy(meta);
                return GST_BASE_TRANSFORM_FLOW_DROPPED;
            case UdfRetCode::UDF_ERROR:
                GST_INFO_OBJECT(udfloader, "Failed to process frame");
                return GST_FLOW_ERROR;
            case UdfRetCode::UDF_FRAME_MODIFIED:
                GST_INFO_OBJECT(udfloader, "UDF_FRAME_MODIFIED");
                modified = true;
                break;
            case UdfRetCode::UDF_OK:
                GST_INFO_OBJECT(udfloader, "UDF_OK");
                break;
            default:
                GST_INFO_OBJECT(udfloader, "Reached default case");
                return GST_FLOW_NOT_SUPPORTED;
            }
        }
        gst_buffer_unmap(buffer, &map);
        msg_envelope_serialized_part_t *parts = NULL;
        if (meta)
        {
            GST_INFO_OBJECT(udfloader, "Attaching frame metadata to buffer");
            int num_parts = msgbus_msg_envelope_serialize(meta, &parts);
            const char *message = parts[0].bytes;
            string metadata(message);
            msgbus_msg_envelope_serialize_destroy(parts, num_parts);
            if (!(gst_json_meta && gst_json_meta->message))
            {
                GVA::VideoFrame gva_frame(buffer, vid_info);
                gva_frame.add_message(metadata);
            }
            else
            {
                set_json_message(gst_json_meta, metadata.c_str());
            }
            msgbus_msg_envelope_destroy(meta);
        }

        GstVideoInfo *renegotiation_info = udfloader->renegotiation_info;
        int width = frame.get_width();
        int height = frame.get_height();
        if (width != renegotiation_info->width || height != renegotiation_info->height)
        {
            GstPad *pad = gst_element_get_static_pad(GST_ELEMENT(udfloader), "src");
            renegotiation_info->width = width;
            renegotiation_info->height = height;
            GstCaps *caps = gst_video_info_to_caps(renegotiation_info);
            GST_INFO_OBJECT(udfloader, "renogotiating caps");
            gst_pad_set_caps(pad, caps);
            gst_object_unref(pad);
            gst_object_unref(caps);
        }
        if (modified)
        {
            GST_DEBUG_OBJECT(udfloader, " replacing data and pushing updated frame");

            gsize size = width * height * 3;

            GstBuffer *buf = gst_buffer_new();
            GstMemory *memory = gst_allocator_alloc(NULL, size, NULL);
            gst_buffer_insert_memory(buf, -1, memory);

            gst_buffer_copy_into(buf, buffer, GST_BUFFER_COPY_METADATA, 0, size);

            if (!gst_buffer_is_writable(buf))
            {
                buf = gst_buffer_make_writable(buf);
                GST_DEBUG_OBJECT(udfloader, "make buffer writable");
            }
            gst_buffer_fill(buf, 0, frame.get_data(), size);
            GstPad *pad = gst_element_get_static_pad(GST_ELEMENT(udfloader), "src");
            gst_pad_push(pad, buf);
            gst_object_unref(pad);
            return GST_BASE_TRANSFORM_FLOW_DROPPED;
        }
        return GST_FLOW_OK;
    }
    catch (const std::exception &e)
    {
        GST_ERROR_OBJECT(udfloader, "%s", e.what());
        gst_buffer_unmap(buffer, &map);
        return GST_FLOW_ERROR;
    }
}
void delete_udfs(GstUDFLoader *udfloader)
{
    if (udfloader->manager)
        delete udfloader->manager;
    GST_INFO_OBJECT(udfloader, "freeing up udfloader element");
}
