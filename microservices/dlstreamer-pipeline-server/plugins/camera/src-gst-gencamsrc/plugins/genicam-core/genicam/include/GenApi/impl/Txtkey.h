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
\brief    Definition of CTxtKey
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_TXTKEY_H
#define GENAPI_TXTKEY_H

#include "../IString.h"
#include "IEEE1212Parser.h"
#include "Node.h"
#include "BaseT.h"
#include "ValueT.h"
#include "StringT.h"
#include "NodeT.h"

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CTxtKey class
    //*************************************************************

    /**
    * \ingroup internal_impl
    *
    * \brief IString implementation for IEEE1212 string entries
    *
    *
    */
    class CTxtKeyImpl : public IString, public CNodeImpl
    {
    public:
        //! Constructor
        CTxtKeyImpl();


    protected:
        //-------------------------------------------------------------
        // IValue implementation
        //-------------------------------------------------------------
        //! Set content of the node as string
        #pragma BullseyeCoverage off
        virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool /*Verify*/)
        {
            //assert(false);
            throw LOGICAL_ERROR_EXCEPTION_NODE("NodeImpl %s can't set value from string  : %s. Use derived class!", m_Name.c_str(), ValueStr.c_str() );
        }
        #pragma BullseyeCoverage on

        //! Get value of the node as string
        virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false);

        virtual EAccessMode InternalGetAccessMode() const;

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIString;
        }


    public:
        //-------------------------------------------------------------
        // Implementation of INodePrivate
        //-------------------------------------------------------------
        //! \name INode implementation
        // \{
        virtual void SetProperty(CProperty &Property);
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        virtual void FinalConstruct();
        // \}

        //-------------------------------------------------------------
        // IString implementation
        //-------------------------------------------------------------
    protected:
        //! Set node value
        virtual void InternalSetValue(const GENICAM_NAMESPACE::gcstring& Value, bool /*Verify = true*/){
            // assert(false);
            throw ACCESS_EXCEPTION_NODE("TxtKey : %s SetValue to %s failed. TxtKey is read only", m_Name.c_str(),Value.c_str() );
        }

        //! Get node value
        virtual GENICAM_NAMESPACE::gcstring InternalGetValue(bool Verify = false, bool IgnoreCache = false);

        //! Retrieves the maximum length of the string in bytes
        virtual int64_t InternalGetMaxLength()
        {
            // assert(false);
            throw ACCESS_EXCEPTION_NODE("TxtKey : %s GetMaxLength failed. TxtKey is read only" );
        }

    protected:
        // inititialize when childs are initialized
        //-------------------------------------------------------------
        // Memeber variables
        //-------------------------------------------------------------


        //! Key of IEEE1212 Configuration Rom entry
        uint16_t m_Key;

        //! most recent Value
        GENICAM_NAMESPACE::gcstring m_Value;

        //! The config rom reader
        CIEEE1212Parser *m_pParser;
    };

    class CTxtKey : public BaseT< ValueT< NodeT< StringT< CTxtKeyImpl > > > >
    {
    };

}

#endif // GENAPI_TXTKEY_H
