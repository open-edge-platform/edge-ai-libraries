#!/bin/bash

. ./license_gate
{
  echo "@@LICENSE-HEADER A | B | C"
  cat ./collection/LICENSE-APACHE-2.0
} | ensure_license_gate
