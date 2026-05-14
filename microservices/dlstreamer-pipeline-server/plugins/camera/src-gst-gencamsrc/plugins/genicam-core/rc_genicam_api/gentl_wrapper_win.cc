/*******************************************************************************
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "gentl_wrapper.h"

#include <string>
#include <sstream>
#include <stdexcept>
#include <cstdlib>
#include <iostream>
#include <cctype>
#include <algorithm>

#include <windows.h>

namespace rcg
{

std::vector<std::string> getAvailableGenTLs(const char *paths)
{
  std::vector<std::string> ret;

  if (paths != 0)
  {
    // split path list into individual paths
    // On Windows, paths are separated by semicolons

    std::stringstream in(paths);
    std::string path;

    while (std::getline(in, path, ';'))
    {
      if (path.size() > 0)
      {
        // Remove leading/trailing whitespace
        size_t start = path.find_first_not_of(" \t\r\n");
        size_t end = path.find_last_not_of(" \t\r\n");
        if (start != std::string::npos)
        {
          path = path.substr(start, end - start + 1);
        }

        if (path.size() > 4 && path.compare(path.size()-4, 4, ".cti") == 0)
        {
          // the given path points to one file ending with .cti
          ret.push_back(path);
        }
        else
        {
          // try to enumerate all files in the given path that end with .cti

          WIN32_FIND_DATAA findData;
          HANDLE findHandle;

          std::string searchPath = path + "\\*.cti";

          findHandle = FindFirstFileA(searchPath.c_str(), &findData);

          if (findHandle != INVALID_HANDLE_VALUE)
          {
            do
            {
              std::string name = findData.cFileName;

              if (name.size() >= 4 && name.compare(name.size()-4, 4, ".cti") == 0)
              {
                ret.push_back(path + "\\" + name);
              }

            } while (FindNextFileA(findHandle, &findData));

            FindClose(findHandle);
          }
        }
      }
    }
  }

  return ret;
}

/**
  Helper to get Windows error as string
*/
static std::string getWindowsErrorString(DWORD errorCode)
{
  char buffer[256];
  FormatMessageA(
    FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
    NULL,
    errorCode,
    MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
    buffer,
    sizeof(buffer),
    NULL
  );
  return std::string(buffer);
}

GenTLWrapper::GenTLWrapper(const std::string &filename)
{
  // open library using LoadLibrary

  lib = (void*)LoadLibraryA(filename.c_str());

  if (lib == NULL)
  {
    DWORD errorCode = GetLastError();
    throw std::invalid_argument(std::string("Cannot open GenTL library: ") + filename +
                                " (Error: " + getWindowsErrorString(errorCode) + ")");
  }

  HMODULE hModule = (HMODULE)lib;

  // Clear any error left by LoadLibraryA (e.g. DllMain side-effects like error 183)
  // so that the final GetLastError() check below only reflects GetProcAddress failures.
  SetLastError(ERROR_SUCCESS);

  // resolve function calls that will only be used privately

  *reinterpret_cast<void**>(&GCInitLib) = (void*)GetProcAddress(hModule, "GCInitLib");
  *reinterpret_cast<void**>(&GCCloseLib) = (void*)GetProcAddress(hModule, "GCCloseLib");

  // resolve public symbols

  *reinterpret_cast<void**>(&GCGetInfo) = (void*)GetProcAddress(hModule, "GCGetInfo");
  *reinterpret_cast<void**>(&GCGetLastError) = (void*)GetProcAddress(hModule, "GCGetLastError");
  *reinterpret_cast<void**>(&GCReadPort) = (void*)GetProcAddress(hModule, "GCReadPort");
  *reinterpret_cast<void**>(&GCWritePort) = (void*)GetProcAddress(hModule, "GCWritePort");
  *reinterpret_cast<void**>(&GCGetPortURL) = (void*)GetProcAddress(hModule, "GCGetPortURL");
  *reinterpret_cast<void**>(&GCGetPortInfo) = (void*)GetProcAddress(hModule, "GCGetPortInfo");

  *reinterpret_cast<void**>(&GCRegisterEvent) = (void*)GetProcAddress(hModule, "GCRegisterEvent");
  *reinterpret_cast<void**>(&GCUnregisterEvent) = (void*)GetProcAddress(hModule, "GCUnregisterEvent");
  *reinterpret_cast<void**>(&EventGetData) = (void*)GetProcAddress(hModule, "EventGetData");
  *reinterpret_cast<void**>(&EventGetDataInfo) = (void*)GetProcAddress(hModule, "EventGetDataInfo");
  *reinterpret_cast<void**>(&EventGetInfo) = (void*)GetProcAddress(hModule, "EventGetInfo");
  *reinterpret_cast<void**>(&EventFlush) = (void*)GetProcAddress(hModule, "EventFlush");
  *reinterpret_cast<void**>(&EventKill) = (void*)GetProcAddress(hModule, "EventKill");
  *reinterpret_cast<void**>(&TLOpen) = (void*)GetProcAddress(hModule, "TLOpen");
  *reinterpret_cast<void**>(&TLClose) = (void*)GetProcAddress(hModule, "TLClose");
  *reinterpret_cast<void**>(&TLGetInfo) = (void*)GetProcAddress(hModule, "TLGetInfo");
  *reinterpret_cast<void**>(&TLGetNumInterfaces) = (void*)GetProcAddress(hModule, "TLGetNumInterfaces");
  *reinterpret_cast<void**>(&TLGetInterfaceID) = (void*)GetProcAddress(hModule, "TLGetInterfaceID");
  *reinterpret_cast<void**>(&TLGetInterfaceInfo) = (void*)GetProcAddress(hModule, "TLGetInterfaceInfo");
  *reinterpret_cast<void**>(&TLOpenInterface) = (void*)GetProcAddress(hModule, "TLOpenInterface");
  *reinterpret_cast<void**>(&TLUpdateInterfaceList) = (void*)GetProcAddress(hModule, "TLUpdateInterfaceList");
  *reinterpret_cast<void**>(&IFClose) = (void*)GetProcAddress(hModule, "IFClose");
  *reinterpret_cast<void**>(&IFGetInfo) = (void*)GetProcAddress(hModule, "IFGetInfo");
  *reinterpret_cast<void**>(&IFGetNumDevices) = (void*)GetProcAddress(hModule, "IFGetNumDevices");
  *reinterpret_cast<void**>(&IFGetDeviceID) = (void*)GetProcAddress(hModule, "IFGetDeviceID");
  *reinterpret_cast<void**>(&IFUpdateDeviceList) = (void*)GetProcAddress(hModule, "IFUpdateDeviceList");
  *reinterpret_cast<void**>(&IFGetDeviceInfo) = (void*)GetProcAddress(hModule, "IFGetDeviceInfo");
  *reinterpret_cast<void**>(&IFOpenDevice) = (void*)GetProcAddress(hModule, "IFOpenDevice");

  *reinterpret_cast<void**>(&DevGetPort) = (void*)GetProcAddress(hModule, "DevGetPort");
  *reinterpret_cast<void**>(&DevGetNumDataStreams) = (void*)GetProcAddress(hModule, "DevGetNumDataStreams");
  *reinterpret_cast<void**>(&DevGetDataStreamID) = (void*)GetProcAddress(hModule, "DevGetDataStreamID");
  *reinterpret_cast<void**>(&DevOpenDataStream) = (void*)GetProcAddress(hModule, "DevOpenDataStream");
  *reinterpret_cast<void**>(&DevGetInfo) = (void*)GetProcAddress(hModule, "DevGetInfo");
  *reinterpret_cast<void**>(&DevClose) = (void*)GetProcAddress(hModule, "DevClose");

  *reinterpret_cast<void**>(&DSAnnounceBuffer) = (void*)GetProcAddress(hModule, "DSAnnounceBuffer");
  *reinterpret_cast<void**>(&DSAllocAndAnnounceBuffer) = (void*)GetProcAddress(hModule, "DSAllocAndAnnounceBuffer");
  *reinterpret_cast<void**>(&DSFlushQueue) = (void*)GetProcAddress(hModule, "DSFlushQueue");
  *reinterpret_cast<void**>(&DSStartAcquisition) = (void*)GetProcAddress(hModule, "DSStartAcquisition");
  *reinterpret_cast<void**>(&DSStopAcquisition) = (void*)GetProcAddress(hModule, "DSStopAcquisition");
  *reinterpret_cast<void**>(&DSGetInfo) = (void*)GetProcAddress(hModule, "DSGetInfo");
  *reinterpret_cast<void**>(&DSGetBufferID) = (void*)GetProcAddress(hModule, "DSGetBufferID");
  *reinterpret_cast<void**>(&DSClose) = (void*)GetProcAddress(hModule, "DSClose");
  *reinterpret_cast<void**>(&DSRevokeBuffer) = (void*)GetProcAddress(hModule, "DSRevokeBuffer");
  *reinterpret_cast<void**>(&DSQueueBuffer) = (void*)GetProcAddress(hModule, "DSQueueBuffer");
  *reinterpret_cast<void**>(&DSGetBufferInfo) = (void*)GetProcAddress(hModule, "DSGetBufferInfo");

  *reinterpret_cast<void**>(&GCGetNumPortURLs) = (void*)GetProcAddress(hModule, "GCGetNumPortURLs");
  *reinterpret_cast<void**>(&GCGetPortURLInfo) = (void*)GetProcAddress(hModule, "GCGetPortURLInfo");
  *reinterpret_cast<void**>(&GCReadPortStacked) = (void*)GetProcAddress(hModule, "GCReadPortStacked");
  *reinterpret_cast<void**>(&GCWritePortStacked) = (void*)GetProcAddress(hModule, "GCWritePortStacked");

  *reinterpret_cast<void**>(&DSGetBufferChunkData) = (void*)GetProcAddress(hModule, "DSGetBufferChunkData");

  *reinterpret_cast<void**>(&IFGetParentTL) = (void*)GetProcAddress(hModule, "IFGetParentTL");
  *reinterpret_cast<void**>(&DevGetParentIF) = (void*)GetProcAddress(hModule, "DevGetParentIF");
  *reinterpret_cast<void**>(&DSGetParentDev) = (void*)GetProcAddress(hModule, "DSGetParentDev");

  *reinterpret_cast<void**>(&DSGetNumBufferParts) = (void*)GetProcAddress(hModule, "DSGetNumBufferParts");
  *reinterpret_cast<void**>(&DSGetBufferPartInfo) = (void*)GetProcAddress(hModule, "DSGetBufferPartInfo");

  // Check if any critical symbol failed to resolve
  DWORD errorCode = GetLastError();
  if (errorCode != ERROR_SUCCESS)
  {
    FreeLibrary(hModule);
    throw std::invalid_argument(std::string("Cannot resolve GenTL symbol: ") +
                                getWindowsErrorString(errorCode));
  }
}

GenTLWrapper::~GenTLWrapper()
{
  if (lib != NULL)
  {
    FreeLibrary((HMODULE)lib);
  }
}

}
