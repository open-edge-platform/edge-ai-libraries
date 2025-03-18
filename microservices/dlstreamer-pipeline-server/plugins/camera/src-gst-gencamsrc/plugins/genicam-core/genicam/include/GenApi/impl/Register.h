//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
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
\brief    Definition of CRegister
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_REGISTER_H
#define GENAPI_REGISTER_H

#include "NodeT.h"
#include "RegisterT.h"
#include "BaseT.h"
#include "ValueT.h"
#include "Port.h"
#include "PrivateTypes.h"
#include "Node.h"
#include "../IInteger.h"
#include "../IEnumeration.h"

namespace GENAPI_NAMESPACE
{

    //! List of EnumInt-node references
    typedef std::list<IValue *> ValueList_t;

    //*************************************************************
    // CRegisterImpl class
    //*************************************************************
    /**
    * \ingroup internal_impl register
    * \brief Standard IRegister implementation
    *  Provides a chunk of memory which acts as a proxy to the register
    */
    class CRegisterImpl
        : public IRegister
        , public CNodeImpl
    {
    public:
        //! Default Contructor
        CRegisterImpl();

    protected:
        //-------------------------------------------------------------
        //! Implements interface IValue (called by IValueT)
        //-------------------------------------------------------------

        //! Get value of the node as string
        virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false);

        //! Set value of the node as string
        virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& valueString, bool Verify = true);

    public:

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIRegister;
        }

        //-------------------------------------------------------------
        // INodePrivate implementation
        //-------------------------------------------------------------

        //! Initializes the object
        virtual void SetInvalid(INodePrivate::ESetInvalidMode simMode);

        //! finalizes the construction of the node
        virtual void FinalConstruct();

        //-------------------------------------------------------------
        // IBase implementation
        //-------------------------------------------------------------

    protected:
        //! Get the access mode of the node
        virtual EAccessMode InternalGetAccessMode() const;

        //-------------------------------------------------------------
        // IRegister implementation
        //-------------------------------------------------------------

        //! Set the register's contents
        virtual void InternalSet(const uint8_t *pBuffer, int64_t Length, bool Verify = true);

        //! Retrieves a pointer to a buffer containing the register's contents
        virtual void InternalGet(uint8_t *ppBuffer, int64_t pLength, bool Verify = false, bool IgnoreCache = false) ;

        //! Retrieves the Length of the register [Bytes]
        virtual int64_t InternalGetLength();

        //! Retrieves the Address of the register
        virtual int64_t InternalGetAddress(bool Verify, bool IgnoreCache);

        //! Get Caching Mode
        virtual ECachingMode InternalGetCachingMode() const;

    public:
        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------
        
        
        virtual void SetProperty(CProperty &Property);
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;


    protected:
        //! Recomputes the Address
        void UpdateAddress(bool Verify, bool IgnoreCache );

        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! pointer to Port node providing access to the port
        CPort *m_pPort;

        //! Address of the register
        int64_t m_Address;

        //! TRue if m_Address is valid
        int64_t m_AddressValid;

        //! Length of the register
        CIntegerPolyRef m_Length;

        //! List of Addresses or pointer to address supplying nodes 
        std::list<CIntegerPolyRef> m_Addresses;

        //! List of Indexes or pointer to address supplying nodes 
        std::list<CIntegerOffsetPolyRef> m_Indexes;

        //! the access mode
        EAccessMode m_AccessMode;
    };



class CRegister
    : public NodeT< RegisterT < ValueT < BaseT < CRegisterImpl > > > >
{};


}

#endif // ifndef GENAPI_REGISTER_H
