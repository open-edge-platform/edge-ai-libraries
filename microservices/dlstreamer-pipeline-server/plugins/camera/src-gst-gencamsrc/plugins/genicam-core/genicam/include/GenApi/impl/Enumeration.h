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
\brief    Definition of CEnumeratorBase and CEnumeration_Int
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_ENUMERATION_H
#define GENAPI_ENUMERATION_H

#include "Base/GCStringVector.h"
#include "Node.h"
#include "../Pointer.h"
#include "BaseT.h"
#include "ValueT.h"
#include "EnumerationT.h"
#include "PolyReference.h"

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // CEnumeration class
    //*************************************************************

    class CEnumerationImpl : public CNodeImpl, public IEnumeration
    {
    public:
        //! Constructor
        CEnumerationImpl();

        //-------------------------------------------------------------
        //! \name INode implementation

        //! Invalidates the node if the polling time has elapsed
        virtual bool Poll( int64_t ElapsedTime );

    protected:
        //! Get the enumeration map
        virtual void InternalGetSymbolics(StringList_t& Symbolics);

        //! Get list of entry nodes
        virtual void InternalGetEntries(NodeList_t & Entries);

        virtual EAccessMode InternalGetAccessMode() const;

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const;

        //! Gets the symbolic value
        virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false);

        //! Sets from symbolic value
        virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true);

        //! Sets the integer value
        virtual void InternalSetIntValue(int64_t Value, bool Verify = true);

        //! Gets the integer value
        virtual int64_t InternalGetIntValue(bool Verify = false, bool IgnoreCache = false );

        //! Get an entry node by name
        virtual IEnumEntry *InternalGetEntryByName(const GENICAM_NAMESPACE::gcstring& Symbolic);

        //! Get an entry node by its IntValue
        virtual IEnumEntry *InternalGetEntry(const int64_t IntValue);

        //! Checks if the value comes from cache or is requested from another node
        virtual bool InternalIsValueCacheValid() const;

        //! True if the AccessMode can be cached
        virtual EYesNo InternalIsAccessModeCacheable() const;

    public:

        virtual void FinalConstruct();

        virtual void SetProperty( CProperty &Property );
        virtual bool GetProperty( CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList ) const;

    protected:
        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! possible stati of the command node
        typedef enum _EStatus
        {
            statusUninitialized,
            statusIdle,
            statusBusy
        } EStatus;

        //! the internal status of the command node
        EStatus m_Status;

        //! the type of the map holding enum entry pointers referenced by the corresponding symbolic name
        typedef std::map<GENICAM_NAMESPACE::gcstring, IEnumEntry*> EnumEntrySymbolicMap_t;

        //! the map holding the enum entries referenced by their symbolic name
        EnumEntrySymbolicMap_t m_EnumEntrySymbolicMap;

        //! the type of the map holding enum entry pointers referenced by the corresponding int value
        typedef std::map<int64_t, IEnumEntry*> EnumEntryIntValueMap_t;

        //! the map holding the enum entries referenced by their int value
        EnumEntryIntValueMap_t m_EnumEntryIntValueMap;

        //! a list holding pointers to the EnumEntries
        NodeList_t m_EnumEntryList;

        //! Reference to the value
        CIntegerPolyRef m_Value;

        //! Value which will be self cleared by the device
        int64_t m_SelfClearingValue;

    private:
        void InternalSetIntValue( IEnumEntry* pEnumEntry, int64_t Value, bool Verify );
    };

    class CEnumeration : public BaseT< ValueT< EnumerationT < NodeT < CEnumerationImpl> > > >
    {
    };

}

#endif // ifndef GENAPI_ENUMERATION_H
