/*******************************************************************************
 * Copyright (C) 2018-2021 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#pragma once

#include "eii/udf/udf_handle.h"
#include "eii/udf/frame.h"
#include <vector>
#include "eii/udf/loader.h"
#include <string>
#include "video_frame.h"
#include <cjson/cJSON.h>

using namespace eii::udf;
using namespace std;

class Manager
{
public:
  Manager(cJSON *json);
  virtual ~Manager();
  std::vector<UdfHandle *> *get_udf_handlers();

private:
  std::vector<UdfHandle *> m_udfs;
  UdfLoader *m_loader;
};