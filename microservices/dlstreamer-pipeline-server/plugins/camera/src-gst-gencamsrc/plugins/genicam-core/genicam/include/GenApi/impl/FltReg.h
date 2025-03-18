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
\brief    Definition of CFltReg
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_FLTREG_H
#define GENAPI_FLTREG_H

#include "../IFloat.h"
#include "FloatT.h"
#include "Register.h"

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CFltReg class
    //*************************************************************

    //! IFloat implementation for a register
    class CFltRegImpl : public IFloat, public CRegisterImpl
    {
    public:
        //! Constructor
        CFltRegImpl();

    protected:

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIFloat;
        }

        //-------------------------------------------------------------
        // IRegister implementation
        //-------------------------------------------------------------

        //! Retrieves the Length of the register [Bytes]
        virtual int64_t InternalGetLength();

        //-------------------------------------------------------------
        // IFloat implementation
        //-------------------------------------------------------------

        //! Set node value
        virtual void InternalSetValue(double dblValue, bool Verify = true);

        //! Get node value
        virtual double InternalGetValue(bool Verify = false, bool IgnoreCache = false);

        //! Get minimum value allowed
        virtual double InternalGetMin() ;

        //! Get maximum value allowed
        virtual double InternalGetMax() ;

        //! True if the float has a constant increment
        virtual bool InternalHasInc()
        {
            // a swiss knife does not know about its increments
            return false;
        }

        //! Get list of valid value
        virtual const double_autovector_t InternalGetListOfValidValues()
        {
            return double_autovector_t();
        }

        //! Get the constant increment if there is any
        #pragma BullseyeCoverage off
        // (untestable, function never called)
        virtual double InternalGetInc()
        {
            assert(false);
            return -1.0;
        }
        #pragma BullseyeCoverage on


        //! Get recommended representation
        virtual  ERepresentation InternalGetRepresentation() const
        {
            if( m_Representation != _UndefinedRepresentation )
                return m_Representation;
            else
                return PureNumber;
        }

        //! Get the unit
        virtual GENICAM_NAMESPACE::gcstring InternalGetUnit() const
        {
            return m_Unit;
        }

        //! Get the way the float should be converted to a string
        virtual EDisplayNotation InternalGetDisplayNotation() const
        {
            return m_DisplayNotation;
        }

        //! Get the precision to be used when converting the float to a string
        virtual int64_t InternalGetDisplayPrecision() const
        {
            return m_DisplayPrecision;
        }

        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------
    public:
    
    virtual void SetProperty( CProperty &Property );
    virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        
    protected:
        //! helper to handle the register access incl. swapping
        void ReadReg(uint8_t* ValueBytes, bool Verify = false, bool IgnoreCache = false);

        //! helper to handle the register access incl. swapping
        void WriteReg(uint8_t* pValueBytes, bool Verify = true);

        //-------------------------------------------------------------
        // Memeber variables
        //-------------------------------------------------------------

        //! The float's reprsentation
        mutable ERepresentation  m_Representation;

        //! endianess of the register
        mutable EEndianess m_Endianess;

        //! the physical unit name
        GENICAM_NAMESPACE::gcstring m_Unit;

        //! the printf format specifier used to convert the float number to a string
        EDisplayNotation m_DisplayNotation;

        //! the precision the float is converted with to a string
        int64_t m_DisplayPrecision;

    };

    //! the clkass implementing the FltReg node
    class CFltReg
        : public BaseT< ValueT< FloatT <  RegisterT < NodeT< CFltRegImpl > > > > >
    {
    };
}

#endif // GENAPI_FLTREG_H
