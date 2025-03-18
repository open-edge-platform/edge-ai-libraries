//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  (c) 2015 by STEMMER IMAGING GmbH
//
//  Project: GenApi
//  Author:  Sascha Dorenbeck
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
\file GenApiNamespace.h
\brief GenICam versioned namespace.
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPI_NAMESPACE_H
#define GENAPI_NAMESPACE_H

#include <GenICamVersion.h>

// This is the development namespace for the GenApi library
#if ! defined(GENAPI_NAMESPACE_DEFINED)

#    if defined(GENICAM_COMPANY_SUFFIX)
#       define GENAPI_NAMESPACE GENICAM_SEP_UNDERSCORE_COMPANY(GenApi, GENICAM_VERSION_MAJOR, GENICAM_VERSION_MINOR, GENICAM_COMPANY_SUFFIX)
#    else
#       define GENAPI_NAMESPACE GENICAM_SEP_UNDERSCORE(GenApi, GENICAM_VERSION_MAJOR, GENICAM_VERSION_MINOR)
#    endif

#    define GENAPI_NAMESPACE_DEFINED
#endif // GENAPI_NAMESPACE_DEFINED

// And make it usable nicely by api's clients
namespace GENAPI_NAMESPACE {}
#if ! defined( GENICAM_SUPPRESS_NAMESPACE_ALIAS )
// Public alias
    namespace GenApi = GENAPI_NAMESPACE;
#endif // GENICAM_SUPPRESS_NAMESPACE_ALIAS

#endif // GENAPI_NAMESPACE_H
