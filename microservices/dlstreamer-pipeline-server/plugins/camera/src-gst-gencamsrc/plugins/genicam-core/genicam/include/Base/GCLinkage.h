//-----------------------------------------------------------------------------
//  (c) 2007 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenICam
//  Author:  Fritz Dierks
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
 \brief    helpers for pragma linkage
 */

#ifndef LINKAGE_H
#define LINKAGE_H

#include <GenICamVersion.h>

#if defined (_MSC_VER)

#   if defined (_WIN32) && defined (_MT )
#     if defined(GENICAM_USER_ALWAYS_LINK_RELEASE)
// for the central installation always the Release version is used
#           define CONFIGURATION "MD"
#     else 
#       if defined(_DEBUG) || defined(DEBUG)
#           define CONFIGURATION "MDd"
#       else
#           define CONFIGURATION "MD"
#       endif
#     endif // defined(GENICAM_USER_ALWAYS_LINK_RELEASE)
#   else
#       error Invalid configuration
#   endif

#   if defined(COMPILER) // COMPILER  may be force set from outside
#       undef GENICAM_COMPILER_STR
#       define GENICAM_COMPILER_STR COMPILER
#   endif

// _MSC_VER==1400 : VC80  : Visual C++ 2005
// _MSC_VER==1500 : VC90  : Visual C++ 2008
// _MSC_VER==1600 : VC100 : Visual C++ 2010
// _MSC_VER==1700 : VC110 : Visual C++ 2012
// _MSC_VER==1800 : VC120 : Visual C++ 2013
// _MSC_VER==1900 : VC140 : Visual C++ 2015
#   if !( _MSC_VER==1400 || _MSC_VER==1500 || _MSC_VER==1600 || _MSC_VER==1700 || _MSC_VER==1800 || _MSC_VER==1900 ) && ! defined(GENICAM_USER_ACCEPTS_ANY_COMPILER)
#     define COMPILER_VERSION_2( s ) #s
#     define COMPILER_VERSION_STRING(version) COMPILER_VERSION_2( version )
#     pragma message( "Notice: Using GenICam with untested compiler, version " COMPILER_VERSION_STRING(_MSC_VER) " detected!" )
#     pragma message( "Following versions were tested: 1400, 1500, 1600, 1700, 1800, 1900." )
#     undef COMPILER_VERSION_2
#     undef COMPILER_VERSION_STRING
#   endif

#   if defined(GENICAM_COMPANY_SUFFIX)
#       define GENICAM_SUFFIX( CONFIGURATION, GENICAM_COMPILER_STR, VERSION_MAJOR, VERSION_MINOR, EXTENSION ) \
            "_" CONFIGURATION "_" GENICAM_COMPILER_STR "_v" VERSION_MAJOR "_" VERSION_MINOR "_" TOSTRING(GENICAM_COMPANY_SUFFIX) "." EXTENSION
#   else
#       define GENICAM_SUFFIX( CONFIGURATION, GENICAM_COMPILER_STR, VERSION_MAJOR, VERSION_MINOR, EXTENSION ) \
            "_" CONFIGURATION "_" GENICAM_COMPILER_STR "_v" VERSION_MAJOR "_" VERSION_MINOR "." EXTENSION
#   endif
        // _MDd_VC80_v3_0_Company
        // _MD_VC80_v3_0_Company
        // _MDd_VC80_v3_0
        // _MD_VC80_v3_0

#   define LIB_SUFFIX \
        GENICAM_SUFFIX( CONFIGURATION, GENICAM_COMPILER_STR, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "lib" )
#if defined(UNDER_RTSS)
#   define DLL_SUFFIX \
        GENICAM_SUFFIX( CONFIGURATION, GENICAM_COMPILER_STR, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "rtdll" )
#else
#   define DLL_SUFFIX \
        GENICAM_SUFFIX( CONFIGURATION, GENICAM_COMPILER_STR, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "dll" )
#endif // defined(UNDER_RTSS)
#   define EXE_SUFFIX \
        GENICAM_SUFFIX( CONFIGURATION, GENICAM_COMPILER_STR, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "exe" )
            
#   define DLL_PREFIX ""

#elif defined (__GNUC__) && (defined (__linux__) || defined(__APPLE__) || defined(VXWORKS))

#   if defined(_DEBUG) || defined(DEBUG)
#      define CONFIGURATION "_d"
#   else
#      define CONFIGURATION ""
#   endif

#   if defined(GENICAM_COMPANY_SUFFIX)
#       define GENICAM_SUFFIX( CONFIGURATION, VERSION_MAJOR, VERSION_MINOR, EXTENSION ) \
            CONFIGURATION "_" GENICAM_COMPILER_STR "_v" VERSION_MAJOR "_" VERSION_MINOR "_" TOSTRING(GENICAM_COMPANY_SUFFIX) "." EXTENSION
#   else
#       define GENICAM_SUFFIX( CONFIGURATION, VERSION_MAJOR, VERSION_MINOR, EXTENSION ) \
            CONFIGURATION "_" GENICAM_COMPILER_STR "_v" VERSION_MAJOR "_" VERSION_MINOR "." EXTENSION
#   endif
        // _d_gcc40_v3_0_Company
        // _gcc40_v3_0_Company
        // _d_gcc40_v3_0
        // _gcc40_v3_0

    
#   define LIB_SUFFIX \
        GENICAM_SUFFIX( CONFIGURATION, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "a" )

#   if defined(__linux__)
#       define DLL_SUFFIX \
            GENICAM_SUFFIX( CONFIGURATION, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "so" )
#   elif defined(VXWORKS)
#       define DLL_SUFFIX \
            GENICAM_SUFFIX( CONFIGURATION, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "out" )
#   else
#       define DLL_SUFFIX \
            GENICAM_SUFFIX( CONFIGURATION, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "dylib" )
#   endif
                
#   define EXE_SUFFIX \
        GENICAM_SUFFIX( CONFIGURATION, GENICAM_VERSION_MAJOR_STR, GENICAM_VERSION_MINOR_STR, "" )

#   if defined(VXWORKS)
#       define DLL_PREFIX ""
#   else
#       define DLL_PREFIX "lib"
#   endif

#else

#   error Unknown shared library support

#endif

#define LIB_NAME( MODULE ) \
    MODULE LIB_SUFFIX

#define DLL_NAME( MODULE ) \
    DLL_PREFIX MODULE DLL_SUFFIX

#define EXE_NAME( MODULE ) \
    MODULE EXE_SUFFIX


// The CameraLink standard defines the names for certain DLLs we build that do not match the GenICam naming scheme
#if defined(_DEBUG) || defined(DEBUG)
#   define CAMERALINK_CONFIGURATION "d"
#else
#   define CAMERALINK_CONFIGURATION ""
#endif
#
#if defined(_MSC_VER)
#   if defined(UNDER_RTSS)
#       define CAMERALINK_DLL_SUFFIX ".rtdll"
#   else
#       define CAMERALINK_DLL_SUFFIX ".dll"
#   endif
#elif defined (__GNUC__) && (defined (__linux__) || defined(__APPLE__) || defined(VXWORKS))
#   if defined(__linux__)
#       define CAMERALINK_DLL_SUFFIX ".so"
#   elif defined(VXWORKS)
#       define CAMERALINK_DLL_SUFFIX ".out"
#   else
#       define CAMERALINK_DLL_SUFFIX ".dylib"
#   endif
#endif
#
#define CAMERALINK_DLL_NAME( MODULE) \
    MODULE CAMERALINK_CONFIGURATION CAMERALINK_DLL_SUFFIX

#endif // LINKAGE_H
