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
\brief    Definition  of CSwissKnife
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_SWISSKNIFE_H
#define GENAPI_SWISSKNIFE_H

#include "../IFloat.h"
#include "Node.h"
#include "MathParser/MathParser.h"
#include "BaseT.h"
#include "ValueT.h"
#include "NodeT.h"
#include "FloatT.h"

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CSwissKnife class
    //*************************************************************

    /**
    * \ingroup internal_impl
    *
    * \brief  Specialized SwissKnife for float nodes
    *
    * Used for formula evaluation with ToPhysical
    * and FromPhysical children
    */
    class CSwissKnifeImpl : public IFloat,  public CNodeImpl
    {
    public:
        //! Constructor
        CSwissKnifeImpl();

        //! Destructor
        virtual ~CSwissKnifeImpl();

    protected:
        //-------------------------------------------------------------
        // IBase implementation
        //-------------------------------------------------------------

        // Get access mode
        virtual EAccessMode InternalGetAccessMode() const;

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIFloat;
        }


    public:
        //-------------------------------------------------------------
        // IInteger implementation
        //-------------------------------------------------------------

        //! Get feature value using m_InputName as hard coded variable name
        /*! This is a helper for the implementation of the converter */
        virtual double GetValueWithInput(double input, bool Verify = false, bool IgnoreCache = false);

    protected:
        //-------------------------------------------------------------
        // IFloat implementation
        //-------------------------------------------------------------

        // Set feature value
        #pragma BullseyeCoverage off
        virtual void InternalSetValue(double /*Value*/, bool /*Verify*/ )
        {
            throw LOGICAL_ERROR_EXCEPTION_NODE("SwissKnife : %s SetValue failed. SwissKnife is read only", m_Name.c_str() );
        }
        #pragma BullseyeCoverage on

        // Get feature value
        virtual double InternalGetValue(bool Verify = false, bool IgnoreCache = false);

        // Get minimum value allowed
        virtual double InternalGetMin()
        {
            return m_Min;
        }

        // Get maximum value allowed
        virtual double InternalGetMax()
        {
            return m_Max;
        }

        //! True if the float has a constant increment
        virtual bool InternalHasInc()
        {
            // a swiss knife does not know about its increments
            return false;
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

        //! Get list of valid value
        const virtual double_autovector_t InternalGetListOfValidValues()
        {
            return double_autovector_t();
        }


        // Get recommended representation
        virtual  ERepresentation InternalGetRepresentation()
        {
            if( m_Representation != _UndefinedRepresentation )
                return m_Representation;
            else
                return PureNumber;
        }

        // Get unit
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
        double  m_Min;

        //! maximum value to be stored in the Register
        double  m_Max;

        //! the formula evaluated by the swiss knife
        GENICAM_NAMESPACE::gcstring m_Formula;

        //! Mapping of the variable's node names to the SYMBOLIC names in the formulas
        std::map<GENICAM_NAMESPACE::gcstring, GENICAM_NAMESPACE::gcstring> m_Symbolics;

        //! Mapping of SYMBOLIC names to the references of the variables
        std::map<GENICAM_NAMESPACE::gcstring, CFloatPolyRef> m_Variables;

        //! the vairble used by th parser
        CStrMap m_VariableMap;

        //! the parser doing the actual work
        CMathParser m_MathParser;

        //! the node's representation
        ERepresentation m_Representation;

        //! the physical unit name
        GENICAM_NAMESPACE::gcstring m_Unit;

        //! the printf format specifier used to convert the float number to a string
        EDisplayNotation m_DisplayNotation;

        //! the precision the float is converted with to a string
        int64_t m_DisplayPrecision;

        //! A hard-coded variable name
        /*! This is a helper for the implementation of the converter */
        GENICAM_NAMESPACE::gcstring m_InputName;

        //! Indicates if the SwissKnife is part of a Converter and shows which direction is implemented
        GENAPI_NAMESPACE::EInputDirection m_InputDirection;

        //! Pointer to the input required when the SwissKnife is used to implement a Converter
        CFloatPolyRef m_Input;

    };

    class CSwissKnife : public BaseT< ValueT< NodeT< FloatT<  CSwissKnifeImpl > > > >
    {
    };

}

#endif // GENAPI_SWISSKNIFE_H
