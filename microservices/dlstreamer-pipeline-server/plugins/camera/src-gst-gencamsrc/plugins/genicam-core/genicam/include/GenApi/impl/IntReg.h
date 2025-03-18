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
\brief    Definition of CIntReg
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_INTREG_H
#define GENAPI_INTREG_H

#include "Register.h"
#include "../IRegister.h"
#include "BaseT.h"
#include "ValueT.h"
#include "NodeT.h"
#include "IntegerT.h"
#include "RegisterT.h"

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CIntRegImpl class
    //*************************************************************

    /**
    * \ingroup internal_impl
    * \brief IInteger implementation for a register
    *
    * Maps an integer (signed or unsigned) to a register
    */
    class CIntRegImpl
        : public IInteger
        , public CRegisterImpl
    {
    public:
        //! Constructor
        CIntRegImpl();

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIInteger;
        }

    protected:

        //-------------------------------------------------------------
        // IRegister implementation
        //-------------------------------------------------------------

        //! Retrieves the Length of the register [Bytes]
        virtual int64_t InternalGetLength();

        //! pre-computes some masks
        void UpdateMasks() const;

        //! if true the masks are valid
        mutable bool m_MasksAreValid;

        //-------------------------------------------------------------
        // IInteger implementation
        //-------------------------------------------------------------

        //! Set feature value
        virtual void InternalSetValue(int64_t Value, bool Verify = true);

        //! Get feature value
        virtual int64_t InternalGetValue(bool Verify = false, bool IgnoreCache = false);

        //! Get minimum value allowed
        virtual int64_t InternalGetMin() const;

        //! Get maximum value allowed
        virtual int64_t InternalGetMax() const;

        //! Get list of valid value
        virtual const int64_autovector_t InternalGetListOfValidValues()
        {
            return int64_autovector_t();
        }

        //! Get increment
        virtual int64_t InternalGetInc() const;

        //! Get recommended representation
        virtual  ERepresentation InternalGetRepresentation() const;

        //! Get the unit
        virtual GENICAM_NAMESPACE::gcstring InternalGetUnit();

        //-------------------------------------------------------------
        // INodePrivate implementation
        //-------------------------------------------------------------

        virtual void SetInvalid(ESetInvalidMode simMode);

    public:
        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------

        
    virtual void SetProperty( CProperty &Property );
    virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        

    protected:
        //! helpers to handle the register access incl. swapping
        void ReadReg(uint8_t* ValueBytes, bool Verify = false, bool IgnoreCache = false);

        //! helpers to handle the register access incl. swapping
        void WriteReg(uint8_t* ValueBytes, bool Verify = true);

        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! minimum value to be stored in the Register
        mutable int64_t  m_Min;

        //! maximum value to be stored in the Register
        mutable int64_t  m_Max;

        //! sign of the integer
        ESign m_Sign;

        //! representation of the integer
        ERepresentation  m_Representation;

        //! the physical unit name
        GENICAM_NAMESPACE::gcstring m_Unit;

        //! endianess of the register
        EEndianess m_Endianess;

        //! The bit indicating the sign of the number to be retrievend
        mutable uint64_t m_SignBit;

        //! The bit to be set to -1 if the number is negative
        mutable uint64_t m_SignMask;

    };

    //! implements the IntReg node
    class CIntReg : public BaseT < ValueT < IntegerT < RegisterT < NodeT <  CIntRegImpl > > > > >
    {
    };
}

#endif // GENAPI_INTREG_H
