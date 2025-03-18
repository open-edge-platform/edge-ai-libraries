//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
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
\brief    declspec's to be used for GenApi Windows dll
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPIDLL_H
#define GENAPIDLL_H

#include <GenApi/GenApiNamespace.h>

#if defined(_MSC_VER)
#   pragma once
#   define GENAPI_DECL_ABSTRACT /*nothing*/
#   ifdef GENAPI_EXPORTS
#       define GENAPI_DECL __declspec(dllexport)
#   else
#       define GENAPI_DECL __declspec(dllimport)
#       define GENAPI_EXPIMP_TEMPL extern
#   endif
#elif defined (__GNUC__) && (defined (__linux__) || defined(__APPLE__) || defined(VXWORKS))
#   define GENAPI_DECL __attribute__((visibility("default"))) 
#   define GENAPI_DECL_ABSTRACT __attribute__((visibility("default"))) 
#   ifdef GENAPI_EXPORTS
        // nothing
#   else
#       define GENAPI_EXPIMP_TEMPL extern
#   endif
#else
#   #error Define how to export symbols on your platform!
#   define GENAPI_DECL
#   ifndef GENAPI_EXPORTS
#       define GENAPI_EXPIMP_TEMPL extern
#   endif
#endif

#endif /* GENAPIDLL_H */
