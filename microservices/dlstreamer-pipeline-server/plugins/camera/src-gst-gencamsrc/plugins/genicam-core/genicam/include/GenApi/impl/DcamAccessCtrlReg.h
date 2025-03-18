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
\brief    Definition of CDcamAccessCtrlReg
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_DCAMACCESSCTRLREG_H
#define GENAPI_DCAMACCESSCTRLREG_H
#if MSC_VER>1000
#pragma once
#endif // MSC_VER>1000
#include "../IInteger.h"
#include "Register.h"
#include "IntegerT.h"
#include <limits>

namespace GENAPI_NAMESPACE
{

    // *************************************************************
    // CDcamAccessCtrlReg class
    // *************************************************************
    /**
    * \ingroup internal_impl
    *
    * \brief Implements the IIDC DCAM Access Control Register for Advanced Features
    *
    * The Access Control Register is implemented as read-only Register. It
    * is the intention to use its IInteger interface in IsEnabled and
    * IsPresent elements.
    * Accessing it via IInteger::GetValue method writes the feature identifier
    * into the register and then checks whether it is locked or not.
    *
    * Currently there is no distinction between node locked and and unlocked
    * features.
    *
    * \todo Caching, Polling obeying the Timeout value
    */
    class CDcamAccessCtrlRegImpl :  public CRegisterImpl, public IInteger
    {
    public:
        CDcamAccessCtrlRegImpl(void);

    protected:
        //-------------------------------------------------------------
        // Implementation of IInteger
        //-------------------------------------------------------------
        //!\name GenApi::IInteger implementation
        //{
        // Set feature value
        virtual void InternalSetValue(int64_t Value, bool Verify = true);

        // Get feature value
        virtual int64_t InternalGetValue(bool Verify = false, bool IgnoreCache = false);

        // Get minimum value allowed
        virtual int64_t InternalGetMin() const;

        // Get maximum value allowed
        virtual int64_t InternalGetMax() const;

        // Get increment
        virtual int64_t InternalGetInc() const;

        //! Get list of valid value
        int64_autovector_t const InternalGetListOfValidValues()
        {
            int64_autovector_t list;
            return list;
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

        //\}
        //-------------------------------------------------------------
        // Implementation of IRegister
        //-------------------------------------------------------------
        //! \name IRegister implementation
        //\{
        virtual void InternalSet(const uint8_t *pBuffer, int64_t Length) const;
        virtual void InternalGet(uint8_t *pBuffer, int64_t Length, bool Verify = false, bool IgnoreCache = false);
        //\}

        //-------------------------------------------------------------
        // Implementation of INode
        //-------------------------------------------------------------
        //! \name INode implementation
        // \{
        virtual EAccessMode InternalGetAccessMode() const;

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIInteger;
        }

        //-------------------------------------------------------------
        // Implementation of INodePrivate
        //-------------------------------------------------------------
        //! \name INode implementation
        // \{
        virtual void SetProperty(CProperty &Property);
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        // \}

	private:
        //! \name Node properties
        //\{
        //! The Feature ID consists of Vendor ID and a advanced feature set unique value
        uint64_t m_FeatureID;
        //! The Timeout value in microseconds. Zero means infinite.
        uint16_t m_Timeout_ms;
        //\}
    };


    class CDcamAccessCtrlReg : public BaseT< ValueT< RegisterT< NodeT< IntegerT< CDcamAccessCtrlRegImpl> > > > >
    {
    };


}

#endif // GENAPI_DCAMACCESSCTRLREG_H
