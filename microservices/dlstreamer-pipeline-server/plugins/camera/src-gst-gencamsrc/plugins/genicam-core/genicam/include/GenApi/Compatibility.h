//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Margret Albrecht
//  $Header$
//
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
    \brief    Definition of macros for cross-platform compatibility
    \ingroup GenApi_Implementation
*/

#ifndef GENAPI_COMPATIBILITY_H
#define GENAPI_COMPATIBILITY_H

#if defined (_MSC_VER) && defined (_WIN32)

#if ! defined(NOMINMAX)
#  define NOMINMAX
#endif

#elif defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__) || defined(VXWORKS))

#  include <stdint.h>
/*
 * Watch out!
 * In order not to break existing code, we have to duplicate the
 * broken MS Windows GUID handling. Never mix with code using the
 * rfc4122-compliant uuid framework implemented by libuuid!
 */

typedef struct _GUID {
    uint32_t Data1;
    uint16_t Data2;
    uint16_t Data3;
    uint8_t  Data4[ 8 ];
} __attribute__ ((packed)) GUID;
#else
#   error Unsupported platform
#endif



#if defined (__APPLE__)
#   define FMT_I64 "ll"
#else
#   if defined (__x86_64) // GNUC && 64 Bit
#       define FMT_I64 "l"
#   else // all 32 bit and all Windows
#       define FMT_I64 "ll"
#   endif
#endif

#endif // ifndef GENAPI_COMPATIBILITY_H
