//-----------------------------------------------------------------------------
//  (c) 2005 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenICam
//  Author:  Fritz Dierks
//  $Header$
//-----------------------------------------------------------------------------
/*!
\file
\brief    helper functions
*/

#ifndef _LOG4CPP_RTSSUTILITIES_H
#define _LOG4CPP_RTSSUTILITIES_H

#include <string>
#if defined (_MSC_VER)
#include <Windows.h>
#endif

#if defined(UNDER_RTSS)

WINBASEAPI BOOL WINAPI DuplicateHandle(
   _In_   HANDLE hSourceProcessHandle,
   _In_   HANDLE hSourceHandle,
   _In_   HANDLE hTargetProcessHandle,
   _Out_  LPHANDLE lpTargetHandle,
   _In_   DWORD dwDesiredAccess,
   _In_   BOOL bInheritHandle,
   _In_   DWORD dwOptions
   );

WINBASEAPI BOOL WINAPI MoveFileExW(
   _In_     LPCWSTR lpExistingFileName,
   _In_opt_ LPCWSTR lpNewFileName,
   _In_     DWORD    dwFlags
   );

WINBASEAPI BOOL WINAPI MoveFileA(
   __in LPCSTR lpExistingFileName,
   __in LPCSTR lpNewFileName
   );

#endif // defined(UNDER_RTSS)


#endif // _LOG4CPP_UTILITIES_H
