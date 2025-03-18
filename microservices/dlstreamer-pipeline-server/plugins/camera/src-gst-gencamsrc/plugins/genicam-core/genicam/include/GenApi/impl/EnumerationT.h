//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Alexander Happe
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
\brief    Definition of the EnumerationT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_ENUMERATIONT_H
#define GENAPI_ENUMERATIONT_H

#include "GenApi/IEnumeration.h"
#include "GenApi/impl/Internal_Compatibility.h"
#include "GenApi/impl/Log.h"
#include "Exception.h"

namespace GENAPI_NAMESPACE
{
    /**
    \brief Implementation of the IEnumeration Interface
    */
    template<class Base>
    class EnumerationT : public Base
    {
    public:
        //! Implementation of IEnumeration::GetSymbolics()
        virtual void GetSymbolics(StringList_t & Symbolics)
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetSymbolics(Symbolics);
        }

        //! Implementation of IEnumeration::GetEntries()
        virtual void GetEntries(NodeList_t & Entries)
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetEntries(Entries);
        }

        //! Implementation of IEnumeration::operator=()
        virtual IEnumeration& operator=(const GENICAM_NAMESPACE::gcstring& ValueStr)
        {
            static_cast<IValue *>(this)->FromString(ValueStr);
            return *this;
        }

        //! Implementation of IEnumeration::SetIntValue()
        virtual void SetIntValue(int64_t Value, bool Verify = true)
        {
            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());
                typename Base::EntryMethodFinalizer E( this, meSetIntValue );

                GCLOGINFOPUSH( Base::m_pValueLog, "SetIntValue( %" FMT_I64 "d )...", Value );

                if( Verify && !IsWritable( this ) )
                    throw ACCESS_EXCEPTION_NODE("Node is not writable.");

                {
                    typename Base::PostSetValueFinalizer PostSetValueCaller(this, CallbacksToFire);  // dtor calls Base::PostSetValue

                    Base::PreSetValue();

                    Base::InternalSetIntValue(Value, Verify);

                    if( Verify )
                        Base::InternalCheckError();

                }

                GCLOGINFOPOP( Base::m_pValueLog, "...SetIntValue" );

                // fire callbacks inside the lock
                std::list<CNodeCallback*>::iterator ptrCallback;
                for( ptrCallback = CallbacksToFire.begin(); ptrCallback != CallbacksToFire.end(); ptrCallback++ )
                {
                    (*ptrCallback)->operator ()(cbPostInsideLock);
                }
            }

            // fire callbacks outside the lock
            std::list<CNodeCallback*>::iterator ptrCallback;
            for( ptrCallback = CallbacksToFire.begin(); ptrCallback != CallbacksToFire.end(); ptrCallback++ )
            {
                (*ptrCallback)->operator ()(cbPostOutsideLock);
            }
        }

        //! Implementation of IEnumeration::operator*()
        virtual GENICAM_NAMESPACE::gcstring operator*()
        {
            return static_cast<IValue *>(this)->ToString();
        }

        //! Implementation of IEnumeration::GetIntValue()
        virtual int64_t GetIntValue(bool Verify = false, bool IgnoreCache = false)
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetIntValue, IgnoreCache );

            GCLOGINFOPUSH( Base::m_pValueLog, "GetIntValue...");

            // Note that readability is tested regardless of Verify
            if( !IsReadable( this ) )
                throw ACCESS_EXCEPTION_NODE("Node is not readable.");

            int64_t IntValue = Base::InternalGetIntValue(Verify, IgnoreCache);

            if( Verify )
                Base::InternalCheckError();

            GCLOGINFOPOP( Base::m_pValueLog, "...GetIntValue = %" FMT_I64 "d", IntValue );

            return IntValue;

        }


        //! Get an entry node by its IntValue
        virtual IEnumEntry *GetEntry(const int64_t IntValue)
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetEntry(IntValue);
        }

        //! Get the current entry
        virtual IEnumEntry *GetCurrentEntry(bool Verify = false, bool IgnoreCache = false)
        {
            AutoLock l(Base::GetLock());

            int64_t Value = GetIntValue(Verify, IgnoreCache);

            return GetEntry(Value);
        }

        //! Implementation of IEnumeration::GetEntryByName()
        virtual IEnumEntry *GetEntryByName(const GENICAM_NAMESPACE::gcstring& Symbolic)
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetEntryByName(Symbolic);
        }


    };

}
#endif
