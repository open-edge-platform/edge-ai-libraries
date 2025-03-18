
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
\brief    Interface to the CStringRegister class.
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_STRINGREGISTER_H
#define GENAPI_STRINGREGISTER_H

#include "GenApi/Types.h"
#include "GenApi/IString.h"
#include "GenApi/impl/Register.h"
#include "GenApi/impl/BaseT.h"
#include "GenApi/impl/ValueT.h"
#include "GenApi/impl/NodeT.h"
#include "GenApi/impl/StringT.h"

//! Part of the generic device API
namespace GENAPI_NAMESPACE
{
    // *************************************************************
    // CStringRegister class
    // *************************************************************
    //! Implements a simple string register
    /**
    *
    * \todo constants length,...
    */
    class CStringRegisterImpl : public CRegisterImpl, public IString
    {
    public:
        CStringRegisterImpl(void);

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIString;
        }


        //-------------------------------------------------------------
        // Implementation of INodePrivate
        //-------------------------------------------------------------
        //! \name INodePrivate implementation
        //\{
        virtual void FinalConstruct();
        //\}
    protected:
        //-------------------------------------------------------------
        // Implementation of IValue
        //-------------------------------------------------------------
        //! \name IValue implementation
        //\{
        virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false);

        //! Set value of the node as string
        virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& valueString, bool Verify = true);
        //\}

        //-------------------------------------------------------------
        // Implementation of IString
        //-------------------------------------------------------------
        //! \name IString implementation
        //\{

        // Set node value
        virtual void InternalSetValue(const GENICAM_NAMESPACE::gcstring& Value, bool Verify = true);

        // Get node value
        virtual GENICAM_NAMESPACE::gcstring InternalGetValue(bool Verify = false, bool IgnoreCache = false);

        //! Retrieves the maximum length of the string in bytes
        virtual int64_t InternalGetMaxLength();
        //\}

    public:
        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------
        
        
    virtual void SetProperty( CProperty &Property );
	virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        
        
    private:
        //IInteger* m_pLength_by;
    };


    class CStringRegister : public BaseT< ValueT< NodeT< StringT< RegisterT< CStringRegisterImpl > > > > >
    {
    };

}

#endif // GENAPI_STRINGREGISTER_H
