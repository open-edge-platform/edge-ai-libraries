//-----------------------------------------------------------------------------
//  (c) 2014 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenICam
//  Author:  Maxime Dupont
//  $Header$
//  License: This file is published under the license of the EMVA GenICam  Standard Group.
//  A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
//  If for some reason you are missing  this file please contact the EMVA or visit the website
//  (http://www.genicam.org) for a full copy.
//
//  THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
//  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
//  OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
//  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
//  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
//  ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
//  POSSIBILITY OF SUCH DAMAGE.
//-----------------------------------------------------------------------------
/*!
\file
\brief    GenICam RTSS utilities
\ingroup Base_PublicUtilities
*/

#ifndef GENAPI_GENAPIRTSSUTILITIES_DEF_H_
#define GENAPI_GENAPIRTSSUTILITIES_DEF_H_

#include "crtdefs.h"
#include <stdio.h>
#include <errno.h>
#include <io.h>
#include "windows.h"

#if defined(UNDER_RTSS) && defined(GENICAM_BUILD)
#if defined(htons)
#undef htons
#endif // defined(htons)

#if defined(ntohs)
#undef ntohs
#endif // defined(ntohs)

#if defined(htonl)
#undef htonl
#endif // defined(htonl)

#if defined(ntohl)
#undef ntohl
#endif // defined(ntohl)


#define HTONS(n) (unsigned short)(((((unsigned short)(n) & 0xFF)) << 8) | (((unsigned short)(n) & 0xFF00) >> 8))
#define NTOHS(n) (unsigned short)(((((unsigned short)(n) & 0xFF)) << 8) | (((unsigned short)(n) & 0xFF00) >> 8))

#define HTONL(n) (unsigned long)(((((unsigned long)(n) & 0xFF)) << 24) | \
                                 ((((unsigned long)(n) & 0xFF00)) << 8) | \
                                 ((((unsigned long)(n) & 0xFF0000)) >> 8) | \
                                 ((((unsigned long)(n) & 0xFF000000)) >> 24))

#define NTOHL(n) (unsigned long)(((((unsigned long)(n) & 0xFF)) << 24) | \
                                 ((((unsigned long)(n) & 0xFF00)) << 8) | \
                                 ((((unsigned long)(n) & 0xFF0000)) >> 8) | \
                                 ((((unsigned long)(n) & 0xFF000000)) >> 24))

#define htons(n) HTONS(n)
#define ntohs(n) NTOHS(n)

#define htonl(n) HTONL(n)
#define ntohl(n) NTOHL(n)

#endif


#if defined(UNDER_RTSS)

#ifdef __cplusplus
extern "C" {
#endif

WINBASEAPI __out HANDLE WINAPI FindFirstFileExW(
   __in       LPCWSTR lpFileName,
   __in       FINDEX_INFO_LEVELS fInfoLevelId,
   __out      LPVOID lpFindFileData,
   __in       FINDEX_SEARCH_OPS fSearchOp,
   __reserved LPVOID lpSearchFilter,
   __in       DWORD dwAdditionalFlags
   );

WINBASEAPI __out HANDLE WINAPI FindFirstFileExA(
   __in       LPCSTR lpFileName,
   __in       FINDEX_INFO_LEVELS fInfoLevelId,
   __out      LPVOID lpFindFileData,
   __in       FINDEX_SEARCH_OPS fSearchOp,
   __reserved LPVOID lpSearchFilter,
   __in       DWORD dwAdditionalFlags
   );

WINBASEAPI BOOL WINAPI FindNextFileW(
   __in  HANDLE hFindFile,
   __out LPWIN32_FIND_DATAW lpFindFileData
   );

WINBASEAPI BOOL WINAPI FindNextFileA(
   __in  HANDLE hFindFile,
   __out LPWIN32_FIND_DATAA lpFindFileData
   );

WINBASEAPI BOOL WINAPI FindClose(
   __inout HANDLE hFindHandle
   );

WINBASEAPI BOOL WINAPI SystemTimeToTzSpecificLocalTime(
   __in_opt CONST TIME_ZONE_INFORMATION * lpTimeZoneInformation,
   __in CONST SYSTEMTIME * lpUniversalTime,
   __out LPSYSTEMTIME lpLocalTime
   ); 

WINBASEAPI UINT WINAPI GetDriveTypeW(
   __in_opt LPCWSTR lpRootPathName
   );

WINBASEAPI UINT WINAPI GetDriveTypeA(
   __in_opt LPCSTR lpRootPathName
   );

WINBASEAPI BOOL WINAPI GetFileInformationByHandle(
   __in HANDLE hFile,
   __out LPBY_HANDLE_FILE_INFORMATION lpFileInformation
   );


WINBASEAPI BOOL WINAPI PeekNamedPipe(
   __in HANDLE hNamedPipe,
   __out_bcount_part_opt(nBufferSize, *lpBytesRead) LPVOID lpBuffer,
   __in DWORD nBufferSize,
   __out_opt LPDWORD lpBytesRead,
   __out_opt LPDWORD lpTotalBytesAvail,
   __out_opt LPDWORD lpBytesLeftThisMessage
   );

WINBASEAPI DWORD WINAPI GetFullPathNameW(
   __in LPCWSTR lpFileName,
   __in DWORD nBufferLength,
   __out_ecount_part_opt(nBufferLength, return +1) LPWSTR lpBuffer,
   __deref_opt_out LPWSTR * lpFilePart
   );

WINBASEAPI BOOL WINAPI SetCurrentDirectoryW(
   __in LPCWSTR lpPathName
   );

WINBASEAPI DWORD WINAPI GetCurrentDirectoryW(
   __in DWORD nBufferLength,
   __out_ecount_part_opt(nBufferLength, return +1) LPWSTR lpBuffer
   );

WINBASEAPI DWORD WINAPI GetFullPathNameA(
   __in LPCSTR lpFileName,
   __in DWORD nBufferLength,
   __out_ecount_part_opt(nBufferLength, return +1) LPSTR lpBuffer,
   __deref_opt_out LPSTR * lpFilePart
   );

WINBASEAPI UINT WINAPI SetErrorMode(
   __in UINT uMode
   );

WINBASEAPI LANGID WINAPI GetUserDefaultLangID(void);


WINBASEAPI DWORD WINAPI GetFileAttributesW(
   __in LPCWSTR lpFileName
   );

WINBASEAPI DWORD WINAPI GetFileAttributesA(
   __in LPCSTR lpFileName
   );

WINBASEAPI BOOL WINAPI GetFileAttributesExW(
   __in LPCWSTR lpFileName,
   __in GET_FILEEX_INFO_LEVELS fInfoLevelId,
   __out LPVOID lpFileInformation
   );

WINBASEAPI BOOL WINAPI GetModuleHandleExA(
   __in DWORD dwFlags,
   __in_opt LPCSTR lpModuleName,
   __out HMODULE * phModule
   );

WINBASEAPI HLOCAL WINAPI LocalFree(
   __deref HLOCAL hMem
   );

WINBASEAPI BOOL WINAPI CopyFileA(
   __in LPCSTR lpExistingFileName,
   __in LPCSTR lpNewFileName,
   __in BOOL bFailIfExists
   );

// ************************************************************************
// **********                   GenAPITest section               **********
// ************************************************************************

WINBASEAPI UINT WINAPI GetSystemDirectoryA(
   __out_ecount_part_opt(uSize, return + 1) LPSTR lpBuffer,
   __in UINT uSize
   );

WINBASEAPI DWORD WINAPI GetTempPathA(
   __in DWORD nBufferLength,
   __out_ecount_part_opt(nBufferLength, return + 1) LPSTR lpBuffer
   );

WINBASEAPI BOOL WINAPI GetThreadTimes(
   __in  HANDLE hThread,
   __out LPFILETIME lpCreationTime,
   __out LPFILETIME lpExitTime,
   __out LPFILETIME lpKernelTime,
   __out LPFILETIME lpUserTime
   );

WINBASEAPI BOOL WINAPI SetConsoleOutputCP(
   __in UINT wCodePageID
   );

WINBASEAPI BOOL WINAPI SetEnvironmentVariableW(
   __in     LPCWSTR lpName,
   __in_opt LPCWSTR lpValue
   );


WINBASEAPI __success(return < nSize) __success(return != 0) DWORD WINAPI GetEnvironmentVariableA(
   __in_opt LPCSTR lpName,
   __out_ecount_part_opt(nSize, return + 1) LPSTR lpBuffer,
   __in DWORD nSize
   );

WINBASEAPI BOOL WINAPI CopyFileW(
   __in LPCWSTR lpExistingFileName,
   __in LPCWSTR lpNewFileName,
   __in BOOL bFailIfExists
   );

#ifdef __cplusplus
}
#endif

#endif // defined(UNDER_RTSS)

#endif // GENAPI_GENAPIRTSSUTILITIES_DEF_H_

