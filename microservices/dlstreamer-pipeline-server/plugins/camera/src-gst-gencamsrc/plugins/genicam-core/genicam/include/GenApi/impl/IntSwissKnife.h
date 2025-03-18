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
\brief    Definition of CIntSwissKnife
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_INTSWISSKNIFE_H
#define GENAPI_INTSWISSKNIFE_H

#include "MathParser/Int64MathParser.h"
#include "PolyReference.h"
#include "Node.h"
#include "BaseT.h"
#include "ValueT.h"
#include "IntegerT.h"
#include "NodeT.h"
#include <map>

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CIntSwissKnife class
    //*************************************************************

    /**
    * \ingroup internal_impl
    *
    * \brief  IInteger implementation for a SwissKnife used for formula evaluation
    */
    class CIntSwissKnifeImpl : public IInteger, public CNodeImpl
    {
    public:
        //! Constructor
        CIntSwissKnifeImpl();

        //! Destructor
        virtual ~CIntSwissKnifeImpl();

    public:

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIInteger;
        }

        //-------------------------------------------------------------
        // IInteger implementation
        //-------------------------------------------------------------

        //! Get feature value using m_InputName as hard coded variable name
        /*! This is a helper for the implementation of the converter */
        virtual int64_t GetValueWithInput(int64_t input, bool Verify = false, bool IgnoreCache = false);


    protected:
        // Get access mode
        virtual EAccessMode InternalGetAccessMode() const;

        //! Set feature value
        #pragma BullseyeCoverage off
        virtual void InternalSetValue(int64_t /*Value*/, bool /* Verify = true */)
        {
            throw ACCESS_EXCEPTION_NODE("IntSwissKnife is read only.");
        }
        #pragma BullseyeCoverage on

        //! Get feature value
        virtual int64_t InternalGetValue(bool Verify = false, bool IgnoreCache = false);


        //! Get minimum value allowed
        virtual int64_t InternalGetMin() const
        {
            return m_Min;
        }

        //! Get maximum value allowed
        virtual int64_t InternalGetMax() const
        {
            return m_Max;
        }

        //! Get list of valid value
        const int64_autovector_t InternalGetListOfValidValues()
        {
            return int64_autovector_t();
        }

        //! Get increment
        virtual int64_t InternalGetInc() const
        {
            return 1LL;
        }

        //! Get recommended representation
        virtual  ERepresentation InternalGetRepresentation() const
        {
            if( m_Representation != _UndefinedRepresentation )
                return m_Representation;
            else
                return PureNumber;
        }

        //! Get the unit
        virtual GENICAM_NAMESPACE::gcstring InternalGetUnit()
        {
            return m_Unit;
        }

        //! Get Caching Mode
        virtual ECachingMode InternalGetCachingMode() const;

    public:
        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------
        
        virtual void FinalConstruct();

        virtual void SetProperty( CProperty &Property );
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        virtual void Parse();
        
    protected:
        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------
        //! minimum value to be stored in the Register
        int64_t  m_Min;

        //! maximum value to be stored in the Register
        int64_t  m_Max;

        //! the formula evaluated by the swiss knife
        GENICAM_NAMESPACE::gcstring m_Formula;

        //! Mapping of the variable's node names to the SYMBOLIC names in the formulas
        std::map<GENICAM_NAMESPACE::gcstring, GENICAM_NAMESPACE::gcstring> m_Symbolics;

        //! Mapping of SYMBOLIC names to the references of the variables
        std::map<GENICAM_NAMESPACE::gcstring, CIntegerPolyRef> m_Variables;

        //! the vairble used by th parser
        CStrMap m_VariableMap;

        //! the parser doing the actual work
        CInt64MathParser m_MathParser;

        //! the representation of this integer node
        ERepresentation m_Representation;

        //! the physical unit name
        GENICAM_NAMESPACE::gcstring m_Unit;

        //! Indicates if the SwissKnife is part of a Converter and shows which direction is implemented
        GENAPI_NAMESPACE::EInputDirection m_InputDirection;

        //! A hard-coded variable name
        /*! This is a helper for the implementation of the converter */
        GENICAM_NAMESPACE::gcstring m_InputName;

        //! Pointer to the input required when the SwissKnife is used to implement a Converter
        CIntegerPolyRef m_Input;

    };

    class CIntSwissKnife : public BaseT< ValueT< NodeT< IntegerT< CIntSwissKnifeImpl > > > >
    {
    };

}

#endif // GENAPI_INTSWISSKNIFE_H
