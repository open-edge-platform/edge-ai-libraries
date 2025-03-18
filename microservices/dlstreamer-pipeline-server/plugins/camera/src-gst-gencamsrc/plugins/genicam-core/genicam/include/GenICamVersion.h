//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenICam
//  Author:  Fritz Dierks
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
\brief    central versioning counters
*/

#ifndef GENICAM_VERSION_H
#define GENICAM_VERSION_H

// The following symbols are defined in a cmake generated include file
//#define GENICAM_VERSION_MAJOR 3 
//#define GENICAM_VERSION_MINOR 0 
//#define GENICAM_VERSION_SUBMINOR 0
//#define GENICAM_MAIN_COMPILER VC120 / gcc421
#include <_GenICamVersion.h>

// The Build is not supported any more
#define GENICAM_VERSION_BUILD 0 

// Normally GENICAM_COMPILER is fed via cmake; however in pure library mode it is not
#ifndef GENICAM_COMPILER
#  define GENICAM_COMPILER GENICAM_MAIN_COMPILER
#endif 

// Don't ask...
#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)
#define GENICAM_RAW_UNDERSCORE(a, b, c) a ## _ ## b ## _ ## c 
#define GENICAM_SEP_UNDERSCORE(a, b, c) GENICAM_RAW_UNDERSCORE(a, b, c)
#define GENICAM_RAW_UNDERSCORE_COMPANY(a, b, c, d) a ## _ ## b ## _ ## c ## _ ## d
#define GENICAM_SEP_UNDERSCORE_COMPANY(a, b, c, d) GENICAM_RAW_UNDERSCORE_COMPANY(a, b, c, d)

// String versions of the version numbers
#define GENICAM_VERSION_MAJOR_STR           TOSTRING( GENICAM_VERSION_MAJOR )
#define GENICAM_VERSION_MINOR_STR           TOSTRING( GENICAM_VERSION_MINOR )
#define GENICAM_VERSION_SUBMINOR_STR        TOSTRING( GENICAM_VERSION_SUBMINOR )
#define GENICAM_VERSION_BUILD_STR           TOSTRING( GENICAM_VERSION_BUILD )
#define GENICAM_COMPILER_STR                TOSTRING( GENICAM_COMPILER )
#define GENICAM_ROOT                        "GENICAM_ROOT"
#define GENICAM_CACHE_VERSION               "GENICAM_CACHE_V" GENICAM_VERSION_MAJOR_STR "_" GENICAM_VERSION_MINOR_STR
#define GENICAM_LOG_CONFIG_VERSION          "GENICAM_LOG_CONFIG_V" GENICAM_VERSION_MAJOR_STR "_" GENICAM_VERSION_MINOR_STR
#define GENICAM_CLPROTOCOL                  "GENICAM_CLPROTOCOL"

#endif // GENICAM_VERSION_H
