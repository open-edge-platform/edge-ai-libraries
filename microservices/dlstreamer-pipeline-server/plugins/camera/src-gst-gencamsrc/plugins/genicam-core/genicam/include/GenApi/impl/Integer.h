//-----------------------------------------------------------------------------
//  (c) 2006-2008 by Basler Vision Technologies
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
    \ingroup GenApi_Implementation
*/

#ifndef GENAPI_INTEGER_H
#define GENAPI_INTEGER_H

#include "../IInteger.h"
#include "Node.h"
#include "BaseT.h"
#include "ValueT.h"
#include "IntegerT.h"
#include "NodeT.h"
#include "PrivateTypes.h"
#include "PolyReference.h"
#include <map>

namespace GENAPI_NAMESPACE
{

    /*!
        \brief Core of the Integer node implementation
        \ingroup GenApi_Implementation
    */
    class CIntegerImpl
        : public IInteger
        , public CNodeImpl
    {
    public:
        //-------------------------------------------------------------
        //! \name Constructor / destructor
        //@{
            //! Constructor
            CIntegerImpl();
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
                return intfIInteger;
            }

        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Interface IInteger (methods are called by the IntegerT class)
        //@{
            //! Set feature value
            virtual void InternalSetValue(int64_t Value, bool Verify = true);

            //! Get feature value
            virtual int64_t InternalGetValue(bool Verify = false, bool IgnoreCache = false );

            //! Get minimum value allowed
            virtual int64_t InternalGetMin();

            //! Get maximum value allowed
            virtual int64_t InternalGetMax();

            //! Get increment
            virtual int64_t InternalGetInc();

	        //! Get list of valid values
            virtual const int64_autovector_t InternalGetListOfValidValues();

            //! Get recommended representation
            virtual  ERepresentation InternalGetRepresentation();

            //! Get the unit
            virtual GENICAM_NAMESPACE::gcstring InternalGetUnit();
        //@}
    public:
        //-------------------------------------------------------------
        //! \name Interface INodePrivate
        //@{
        //! finishes the constriction of the node
        virtual void FinalConstruct();

        //! Get Caching Mode
        virtual ECachingMode InternalGetCachingMode() const;
        //@}

        virtual void SetInvalid(ESetInvalidMode simMode);

    public:

    virtual void SetProperty( CProperty &Property );
    virtual bool GetProperty( CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList ) const;
    


    protected:
        //-------------------------------------------------------------
        //! \name Property variables
        //@{
            //! List storing the main value and the copy values
            std::list<CIntegerPolyRef> m_ValuesCopy;

            //! References to the main value inside m_ValuesCopy
            std::list<CIntegerPolyRef>::iterator m_pMainValue;

            //! Map storing the indexed values by index
            std::map<int64_t, CIntegerPolyRef> m_ValuesIndexed;

            //! Reference to the default value which is used if the index has no matching entry
            CIntegerPolyRef m_ValueDefault;

            //! Reference to the minimum value
            CIntegerPolyRef m_Min;

            //! Reference to the maximum value
            CIntegerPolyRef m_Max;

            //! Reference to the increment value
            CIntegerPolyRef m_Inc;

            //! Reference to the index value
            CIntegerPolyRef m_Index;

            //! recommended representation of the value
            ERepresentation m_Representation;

            //! the physical unit name
            GENICAM_NAMESPACE::gcstring m_Unit;

            //! The list of valid values for the integer.
            int64_autovector_impl m_ValidValueSet;

        //@}
    };

    /*!
        \brief Integer node implementation
        \ingroup GenApi_Implementation
    */
    class CInteger : public BaseT< ValueT< IntegerT< NodeT < CIntegerImpl> > > >
    {
    };

}

#endif // GENAPI_INTEGER_H
