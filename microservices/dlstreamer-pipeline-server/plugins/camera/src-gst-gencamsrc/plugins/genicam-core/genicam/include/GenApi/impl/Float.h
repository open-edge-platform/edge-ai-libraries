//-----------------------------------------------------------------------------
//  (c) 2006-8 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Hartmut Nebelung, Fritz Dierks
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
    \ingroup GenApi_Implementation
*/

#ifndef GENAPI_FLOAT_H
#define GENAPI_FLOAT_H

#include "Base/GCString.h"
#include "../IFloat.h"
#include "Node.h"
#include "BaseT.h"
#include "ValueT.h"
#include "NodeT.h"
#include "FloatT.h"
#include <map>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4275 ) // non dll-interface XXX used as base for  dll-interface class YYY
#endif

namespace GENAPI_NAMESPACE
{

    /*! \brief Core pf the Float node implementation
        \ingroup GenApi_Implementation
    */
    class CFloatImpl : public IFloat, public CNodeImpl
    {
    public:
        //-------------------------------------------------------------
        //! \name Constructor / destructor
        //@{
            //! Constructor
            CFloatImpl();
        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Interface IBase (methods are called by the BaseT class)
        //@{
            //! Get the access mode of the node
            virtual EAccessMode InternalGetAccessMode() const;

            //! Implementation of IBase::GetPrincipalInterfaceType()
            virtual EInterfaceType InternalGetPrincipalInterfaceType() const
            {
                return intfIFloat;
            }
        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Interface IFloat (methods are called by the FloatT class)
        //@{
            //! Set feature value
            virtual void InternalSetValue(double Value, bool Verify = true);

            //! Get feature value
            virtual double InternalGetValue(bool Verify = false, bool IgnoreCache = false) const;

            //! Get minimum value allowed
            virtual double InternalGetMin() const;

            //! Get maximum value allowed
            virtual double InternalGetMax() const;

            //! True if the float has a constant increment
            virtual bool InternalHasInc();

            //! Get the constant increment if there is any
            virtual double InternalGetInc();

            //! Get list of valid value
            virtual const double_autovector_t InternalGetListOfValidValues();

            //! Get recommended representation
            virtual  ERepresentation InternalGetRepresentation() const;

            //! Get the unit
            virtual GENICAM_NAMESPACE::gcstring InternalGetUnit() const;

            //! Get the way the float should be converted to a string
            virtual EDisplayNotation InternalGetDisplayNotation() const;

            //! Get the precision to be used when converting the float to a string
            virtual int64_t InternalGetDisplayPrecision() const;
        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Interface INode (methods are called by the NodeT class)
        //@{

        //! Get Caching Mode
        virtual ECachingMode InternalGetCachingMode() const;
        //@}


        virtual void SetInvalid(ESetInvalidMode simMode);

    //-------------------------------------------------------------
    // Initializing
    //-------------------------------------------------------------
    public:

        
    virtual void SetProperty( CProperty &Property );
    virtual bool GetProperty( CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList ) const;
    
    protected:
        //-------------------------------------------------------------
        //! \name Property variables
        //@{
            //! Map storing the indexed values by index
            std::map<int64_t, CFloatPolyRef> m_ValuesIndexed;

            //! The value
            CFloatPolyRef m_ValueDefault;

            //! The value
            CFloatPolyRef m_Value;

            //! The minimum value
            CFloatPolyRef m_Min;

            //! The maximum value
            CFloatPolyRef m_Max;

            //! The constant increment if there is any
            CFloatPolyRef m_Inc;

            //! Reference to the index value
            CIntegerPolyRef m_Index;

            //! recommended representation of the value
            mutable ERepresentation m_Representation;

            //! the physical unit name
            GENICAM_NAMESPACE::gcstring m_Unit;

            //! the printf format specifier used to convert the float number to a string
            EDisplayNotation m_DisplayNotation;

            //! the precision the float is converted with to a string
            int64_t m_DisplayPrecision;

        //@}
    };

    /*! \brief Float node implementation
        \ingroup GenApi_Implementation
    */
    class CFloat
        : public BaseT< ValueT< NodeT < FloatT < CFloatImpl > > > >
    {
    };
}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // GENAPI_FLOAT_H
