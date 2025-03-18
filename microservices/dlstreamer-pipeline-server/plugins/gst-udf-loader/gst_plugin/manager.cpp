/*******************************************************************************
 * Copyright (C) 2018-2021 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "manager.h"

#include <fstream>
#include <limits.h>
#include <regex>

#include <eii/utils/json_config.h>
#include <eii/utils/config.h>

#include <iostream>
#include <dlfcn.h>
#include <typeinfo>

void free_fn(void *ptr)
{
    config_value_t *obj = (config_value_t *)ptr;
    config_value_destroy(obj);
}

config_value_t *get_value(const void *cfg, const char *key)
{
    config_value_t *obj = (config_value_t *)cfg;
    return config_value_object_get(obj, key);
}

Manager::Manager(cJSON *json)

{
    dlopen("libpython3.10.so.1.0", RTLD_LAZY | RTLD_GLOBAL);
    m_loader = new UdfLoader();

    config_t *config = config_new(
        (void *)json, free_json,
        get_config_value, set_config_value);

    config_value_t *udfs = NULL;
    udfs = config_get(config, "udfs");
    if (udfs == NULL)
    {
        throw "Failed to get UDFs";
    }

    if (udfs->type != CVT_ARRAY)
    {
        config_value_destroy(udfs);
        throw "udfs must be an array";
    }

    int len = (int)config_value_array_len(udfs);

    for (int i = 0; i < len; i++)
    {
        config_value_t *cfg_obj = config_value_array_get(udfs, i);
        if (cfg_obj == NULL)
        {
            throw "Failed to get configuration array element";
        }
        if (cfg_obj->type != CVT_OBJECT)
        {
            throw "UDF configuration must be objects";
        }
        config_value_t *name = config_value_object_get(cfg_obj, "name");
        if (name == NULL)
        {
            throw "Failed to get UDF name";
        }
        if (name->type != CVT_STRING)
        {
            throw "UDF name must be a string";
        }

        void (*free_ptr)(void *) = NULL;
        if (cfg_obj->body.object->free == NULL)
        {
            free_ptr = free_fn;
        }
        else
        {
            free_ptr = cfg_obj->body.object->free;
        }
        config_t *cfg = config_new(
            (void *)cfg_obj, free_ptr, get_value, NULL);
        if (cfg == NULL)
        {
            throw "Failed to initialize configuration for UDF";
        }

        cout << "Loading UDF..." << endl;
        cout << name->body.string << endl;

        UdfHandle *handle = m_loader->load(name->body.string, cfg, 1);
        if (handle == NULL)
        {
            throw "Failed to load UDF";
        }
        config_value_destroy(name);
        m_udfs.push_back(handle);
    }
    config_value_destroy(udfs);
}

Manager::~Manager()
{
    for (auto handle : m_udfs)
    {
        delete handle;
    }
    m_udfs.clear();
    if (m_loader)
        delete m_loader;
    m_loader = NULL;
}

std::vector<UdfHandle *> *Manager::get_udf_handlers()
{
    return &m_udfs;
}
