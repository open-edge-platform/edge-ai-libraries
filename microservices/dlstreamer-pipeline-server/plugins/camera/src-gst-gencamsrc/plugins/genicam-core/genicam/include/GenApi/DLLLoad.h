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
\brief    Definition of function for laoding a DLL dynamically
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPI_DLLLOAD_H
#define GENAPI_DLLLOAD_H

#include <GenApi/INodeMap.h>
#include <GenApi/GenApiVersion.h>

#if defined (_MSC_VER)
// nothing
#elif defined (__GNUC__)
#  if !defined(__x86_64) && !defined(__arm__) && !defined(VXWORKS)
#   define  __cdecl __attribute__((cdecl))
#  else
#   define  __cdecl /* use default calling convention */
#  endif
#else
#   error Unsupported compiler
#endif

namespace GENAPI_NAMESPACE
{
    //! Function prototype for the create function implemented by GenApi DLLs
    //! \ingroup GenApi_PublicImpl
    typedef INodeMap* (__cdecl * Create_f)(const char* pDeviceName);

    //! Function prototype for checking the DLL's GenApi version
    //! \ingroup GenApi_PublicImpl
    typedef void (__cdecl * GetGenApiVersion_f)(Version_t &Version);

    //! Frees static resources hold by GenApi
    /*! Frees all dynamically loaded DLLs held by the DLLManager
    */
    GENAPI_DECL void GenApiTerminate();
}

#endif // ifndef GENAPI_DLLLOAD_H
