
//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Hartmut Nebelung
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
\brief    Interface to the CSmartFeature class.
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_SMARTFEATURE_H
#define GENAPI_SMARTFEATURE_H

#include "../Types.h"
#include "../IInteger.h"
#include "Register.h"
#include "BaseT.h"
#include "ValueT.h"
#include "NodeT.h"
#include "IntegerT.h"


//! Part of the generic device API
namespace GENAPI_NAMESPACE
{
    // *************************************************************
    // CSmartFeature class
    // *************************************************************
    //! Implements the Basler Smart Feature class
    /**
    * Intention is to use this class in pIsAvailable and pIsImplemented
    * elements where the GetValue method is called in a boolean sense.
    * But also to use it as an address register.
    *
    */
    class CSmartFeatureImpl : public CRegisterImpl, public IInteger
    {
    public:
        CSmartFeatureImpl(void);

    protected:
        //-------------------------------------------------------------
        // Implementation of IInteger
        //-------------------------------------------------------------
        //!\name GenApi::IInteger implementation
        //{
        // Set feature value
        virtual void InternalSetValue(int64_t /*Value*/, bool /*Verify = true*/)
        {
            throw ACCESS_EXCEPTION_NODE("CSmartFeatureImpl::InternalSetValue : a smart feature cannot be written");
        }

        // Get feature value
        virtual int64_t InternalGetValue(bool Verify = false, bool IgnoreCache = false);

        // Get minimum value allowed
        virtual int64_t InternalGetMin() const;

        // Get maximum value allowed
        virtual int64_t InternalGetMax() const;

        // Get increment
        virtual int64_t InternalGetInc() const;

        //! Get list of valid value
        const int64_autovector_t InternalGetListOfValidValues()
        {
            return int64_autovector_t();
        }

        // Get recommended representation
        virtual  ERepresentation InternalGetRepresentation() const
        {
            return PureNumber;
        }

        //! Get the unit
        virtual GENICAM_NAMESPACE::gcstring InternalGetUnit()
        {
            return GENICAM_NAMESPACE::gcstring();
        }

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIInteger;
        }


        //\}
        //-------------------------------------------------------------
        // Implementation of INode
        //-------------------------------------------------------------
        //! \name INode implementation
        // \{
        virtual EAccessMode InternalGetAccessMode() const;
        // \}

		//-------------------------------------------------------------
		// Implementation of INodePrivate
		//-------------------------------------------------------------
		//! \name INode implementation
		// \{
		virtual void SetProperty(CProperty &Property);
		virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
		// \}

    private:
        //! the GUID identifying the smart features
        GUID m_FeatureID;
    };

    class CSmartFeature : public BaseT< ValueT< NodeT< IntegerT< RegisterT< CSmartFeatureImpl > > > > >
    {
    };
}
#endif // GENAPI_SMARTFEATURE_H
