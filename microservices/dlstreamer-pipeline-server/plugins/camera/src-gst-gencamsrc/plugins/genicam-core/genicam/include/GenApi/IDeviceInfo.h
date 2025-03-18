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
\brief  Definition of interface INodeMap
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_DEVICEINFO_H
#define GENAPI_DEVICEINFO_H

#include <Base/GCBase.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // IDeviceInfo interface
    //*************************************************************

    /**
    \brief Interface to get information about the device (= nodemap)
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IDeviceInfo
    {
        //! Get the model name
        virtual GENICAM_NAMESPACE::gcstring GetModelName() = 0;

        //! Get the vendor name
        virtual GENICAM_NAMESPACE::gcstring GetVendorName() = 0;

        //! Get tool tip
        virtual GENICAM_NAMESPACE::gcstring GetToolTip() = 0;

        //! Get the standard name space
        virtual GENICAM_NAMESPACE::gcstring GetStandardNameSpace() = 0;

        //! Get the version of the DLL's GenApi implementation
        virtual void GetGenApiVersion(Version_t &Version, uint16_t &Build) = 0;

        //! Get the schema version number
        virtual void GetSchemaVersion(Version_t &Version) = 0;

        //! Get the version of the device description file
        virtual void GetDeviceVersion(Version_t &Version) = 0;

        //! Get the Guid describing the product
        virtual GENICAM_NAMESPACE::gcstring GetProductGuid() = 0;

        //! Get the Guid describing the product version
        virtual GENICAM_NAMESPACE::gcstring GetVersionGuid() = 0;
    };
}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IDEVICEINFO_H
