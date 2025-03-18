/****************************************************************************
(c) 2004 by Basler Vision Technologies
(c) 2005 STEMMER IMAGING

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


****************************************************************************/

/// \file
/// \brief    Platform-dependent type definitions
/// \ingroup Base_PublicUtilities


#ifndef GENICAM_TYPES_H
#define GENICAM_TYPES_H

#include <Base/GCNamespace.h>

// Make sure WIN32 is defined if the toolchain does not already do it.
#if defined (_WIN32) && !defined(WIN32)
#    define WIN32
#endif

#if !defined (_WIN32)

#    ifndef __STDC_LIMIT_MACROS
#       define  __STDC_LIMIT_MACROS
#    endif

#    ifndef __STDC_CONSTANT_MACROS
#       define  __STDC_CONSTANT_MACROS
#    endif

#    include <stddef.h>
#ifndef VXWORKS
#    include <inttypes.h>
#endif
#    include <stdint.h>

#elif defined (_WIN32)

//! \addtogroup Base_PublicUtilities
//! \{

// tag to perform 64 compatibility warnings checks on a type
#   if !defined(GC_W64)
#       if defined(_M_IX86) && _MSC_VER >= 1300
#           define GC_W64 __w64
#       else
#           define GC_W64
#       endif
#   endif

#   if defined(_MSC_VER) && _MSC_VER >= 1600
        // VS2010 provides stdint.h
#       include <stdint.h>
#   else
#       ifndef _STDINT // only define if not already done

            //! makes int 8 portable across different platforms
            typedef char int8_t;
            //! makes unsigned char portable across different platforms
            typedef unsigned char uint8_t;

            //! makes short portable across different platforms
            typedef short int16_t;
            //! makes unsigned short portable across different platforms
            typedef unsigned short uint16_t;

            //! makes __int32 portable across different platforms
            typedef __int32 int32_t;
            //! makes unsigned int32 portable across different platforms
            typedef unsigned __int32 uint32_t;

            //! makes int64 portable across different platforms
            typedef __int64 int64_t;
            //! makes unsigned int64 portable across different platforms
            typedef unsigned __int64 uint64_t;

#       endif // _STDINT
#    endif // _MSC_VER >= 1600

    // Deprecated, use int8_t instead
    // typedef char char8_t;

    // Deprecated, use uint8_t instead
    // typedef unsigned char uchar8_t;

    //! use a universal platform dependent int
    typedef __int64 int_t;
    //! use a universal platform dependent unsigned int
    typedef unsigned __int64 uint_t;

#   ifndef _SIZE_T_DEFINED
#       ifdef  _WIN64
            //! use a universal platform dependent unsigned int
            typedef unsigned __int64 size_t;
#       else
            //! use a universal platform dependent unsigned int
            typedef GC_W64 unsigned int size_t;
#       endif
#       define _SIZE_T_DEFINED
#   endif

#   ifndef _INTPTR_T_DEFINED
#       ifdef  _WIN64
            //! use a universal platform dependent intptr_t
            typedef __int64 intptr_t;
#       else
            //! use a universal platform dependent intptr_t
            typedef GC_W64 int intptr_t;
#       endif
#       define _INTPTR_T_DEFINED
#   endif

#   ifndef _UINTPTR_T_DEFINED
#       ifdef  _WIN64
            //! use a universal platform dependent uintptr_t
            typedef unsigned __int64 uintptr_t;
#       else
            //! use a universal platform dependent intptr_t
            typedef GC_W64 unsigned int uintptr_t;
#       endif
#       define _UINTPTR_T_DEFINED
#   endif

#else
#   error No platform-specific type definitions
#endif /* __unix__ */

// \}


#ifndef GC_INT64_MAX
#ifdef INT64_MAX
#   define GC_INT64_MAX   INT64_MAX
#else
#   define GC_INT64_MAX   static_cast<int64_t>(0x7fffffffffffffffLL)    /* maximum signed int64 value */
#endif
#endif // GC_INT64_MAX

#ifndef GC_INT64_MIN
#ifdef INT64_MIN
#   define GC_INT64_MIN   INT64_MIN
#else
#   define GC_INT64_MIN   static_cast<int64_t>(0x8000000000000000LL)    /* minimum signed int64 value */
#endif
#endif // GC_INT64_MIN

#ifndef GC_UINT64_MAX
#ifdef UINT64_MAX
#   define GC_UINT64_MAX  UINT64_MAX
#else
#   define GC_UINT64_MAX  static_cast<uint64_t>(0xffffffffffffffffULL)   /* maximum unsigned int64 value */
#endif
#endif // GC_UINT64_MAX

#ifndef GC_INT32_MAX
#ifdef INT32_MAX
#   define GC_INT32_MAX   INT32_MAX
#else
#   define GC_INT32_MAX   static_cast<int64_t>(0x000000007fffffffLL)    /* maximum signed int32 value */
#endif
#endif // GC_INT32_MAX

#ifndef GC_INT32_MIN
#ifdef INT32_MIN
#   define GC_INT32_MIN   INT32_MIN
#else
#   define GC_INT32_MIN   static_cast<int64_t>(0xffffffff80000000LL)    /* minimum signed int32 value */
#endif
#endif // GC_INT32_MIN

#ifndef GC_UINT32_MAX
#ifdef UINT32_MAX
#   define GC_UINT32_MAX  UINT32_MAX
#else
#   define GC_UINT32_MAX  static_cast<uint64_t>(0x00000000ffffffffULL)   /* maximum unsigned int32 value */
#endif
#endif // GC_UINT32_MAX

#ifndef GC_INT8_MAX
#ifdef INT8_MAX
#   define GC_INT8_MAX    INT8_MAX
#else
#   define GC_INT8_MAX    static_cast<int64_t>(0x000000000000007fLL)    /* maximum signed int8 value */
#endif
#endif // GC_INT8_MAX

#ifndef GC_INT8_MIN
#ifdef INT8_MIN
#   define GC_INT8_MIN    INT8_MIN
#else
#   define GC_INT8_MIN    static_cast<int64_t>(0xffffffffffffff80LL)    /* minimum signed int8 value */
#endif
#endif // GC_INT8_MIN

#ifndef GC_UINT8_MAX
#ifdef UINT8_MAX
#   define GC_UINT8_MAX   UINT8_MAX
#else
#   define GC_UINT8_MAX   static_cast<uint64_t>(0x00000000000000ffULL)   /* maximum unsigned int8 value */
#endif
#endif // GC_UINT8_MAX

//! \addtogroup Base_PublicUtilities
//! \{

// Utility Types

// Deprecated, use const uint8_t* instead
// typedef const char *      pcchar8_t;

// Deprecated, use uint8_t* instead
// typedef char *            pchar8_t;

//! 32 bit floating point
typedef float             float32_t;

//! 64 bit floating point
typedef double            float64_t;

//! \}

// gc base import/export
#if defined(_MSC_VER)
#   ifdef GCBASE_EXPORTS
#       define GCBASE_API __declspec( dllexport )
#       define GCBASE_RTTI_CLASS_API __declspec( dllexport )
#   else
#       define GCBASE_API __declspec( dllimport )
#       define GCBASE_RTTI_CLASS_API __declspec( dllimport )
#   endif
#elif defined (__GNUC__)
#   ifdef GCBASE_EXPORTS
#          define GCBASE_API __attribute__((visibility("default")))
#          define GCBASE_RTTI_CLASS_API __attribute__((visibility("default")))
#   else
#      define GCBASE_API
       // Classes that need RTTI info across library boundaries (like Exception classes)
       // need to always use default visibility, even when symbols are being imported.
#      define GCBASE_RTTI_CLASS_API __attribute__((visibility("default")))
#   endif
#else
#   error Unsupported compiler or platform
#endif

namespace GENICAM_NAMESPACE
{
    //! version
    struct GCBASE_API Version_t
    {
        uint16_t Major;        //!> a is incompatible with b if a != b
        uint16_t Minor;        //!> a is incompatible b a > b
        uint16_t SubMinor;     //!> a is aways compatible with b
    };
}

using GENICAM_NAMESPACE::Version_t;

// mark a variable as unused. This prevents unused parameter/ unused local variable warnings on warning level 4.
#if defined(_MSC_VER)
#   define GC_UNUSED(unused_var) (void)(unused_var)
#elif defined(__GNUC__)
#   define GC_UNUSED(unused_var) // no changes to unused params with GCC
#else
#   error Unsupported compiler or platform
#endif


#endif // GENICAM_TYPES_H
