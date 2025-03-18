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
\brief    Definition of CBoolean
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_BOOLEAN_H
#define GENAPI_BOOLEAN_H

#include "../IBoolean.h"
#include "Node.h"
#include "BooleanT.h"
#include "ValueT.h"
#include "BaseT.h"
#include "NodeT.h"
#include "PolyReference.h"

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // CBoolean class
    //*************************************************************

    /*!
    * \brief IBoolean implementation
    *
    * May be used as a toggle. The Values for On and Off may be chosen.
    * Supposed to work together with a IInteger node, e.g. CMaskedInt,
    * for setting the concrete values.
    */

    class CBooleanImpl : public  IBoolean, public CNodeImpl
    {
    public:
        //! Constructor
        CBooleanImpl();


    protected:
        //-------------------------------------------------------------
        //! \name Interface IBase (methods are called by the BaseT class)
        //! \ingroup GenApi_Implementation
        //@{
            //  Get the access mode of the node
            virtual EAccessMode InternalGetAccessMode() const;

            //! Implementation of IBase::GetPrincipalInterfaceType()
            virtual EInterfaceType InternalGetPrincipalInterfaceType() const
            {
                return intfIBoolean;
            }
        //@}


        //-------------------------------------------------------------
        //! \name Interface IValue (methods are called by the ValueT class)
        //! \ingroup GenApi_Implementation
        //@{

            //! Checks if the value comes from cache or is requested from another node
            virtual bool InternalIsValueCacheValid() const;

        //@}

        //-------------------------------------------------------------
        //! \name Implementation of GenApi::IBoolean interface
        //! \ingroup GenApi_Implementation
        //@{
            // Set node value
            virtual void InternalSetValue(bool Value, bool Verify = true);

            // Get node value
            virtual bool InternalGetValue(bool Verify = false, bool IgnoreCache = false) const;
        //@}

        //! \name Implementation of GenApi::IValue interface
        //! \ingroup GenApi_Implementation
        //@{
            // Get value of the node as string
            virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false);

            // Set value of the node as string
            virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& valueString, bool Verify = true);
        //@}

    public:
        virtual void FinalConstruct();
        
        
        virtual void SetProperty( CProperty &Property );
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;

    protected:

        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! Reference to vlaue
        CIntegerPolyRef m_Value;

        //! Value for On
        int64_t m_OnValue;

        //! Value for Off
        int64_t m_OffValue;

    };


    class CBoolean : public BaseT< ValueT< BooleanT<  NodeT < CBooleanImpl> > > >
    {
    };

}

#endif // GENAPI_BOOLEAN_H
