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
\brief    Definition of the ValueT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_VALUET_H
#define GENAPI_VALUET_H

#include "GenApi/NodeCallback.h"
#include "../IValue.h"
#include "Base/GCException.h"
#include "GenApi/impl/Log.h"
#include "../Synch.h"


namespace GENAPI_NAMESPACE
{

    /**
    \brief Implementation of the IValue interface
    */
    template< class Base>
    class ValueT
        : public Base
    {
    public:

        //! Implementation of IValue::ToString()
        virtual GENICAM_NAMESPACE::gcstring ToString(bool Verify = false, bool IgnoreCache = false)
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meToString, IgnoreCache );

            GCLOGINFOPUSH( Base::m_pValueLog, "ToString...");

            // Note that readability is tested regardless of Verify
            if( !IsReadable( this ) )
                throw ACCESS_EXCEPTION_NODE("Node is not readable");

            GENICAM_NAMESPACE::gcstring ValueStr = Base::InternalToString(Verify, IgnoreCache);

            if( Verify )
                Base::InternalCheckError();

            GCLOGINFOPOP( Base::m_pValueLog, "...ToString = %s", ValueStr.c_str() );

            return ValueStr;
        }

        //! Implementation of IValue::FromString()
        virtual void FromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true)
        {
            // a list of callbacks to fire held outside the lock-guarded area on the stack
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());
                typename Base::EntryMethodFinalizer E( this, meFromString );

                if( Verify && !IsWritable( this ) )
                    throw ACCESS_EXCEPTION_NODE("Node is not writable");

                GCLOGINFO( Base::m_pValueLog, "FromString = '%s' ", ValueStr.c_str() );

                {
                    typename Base::PostSetValueFinalizer PostSetValueCaller(this, CallbacksToFire);  // dtor calls Base::PostSetValue

                    Base::PreSetValue(); // invalidates all nodes if this is the first call in a chain of SetValue-like calls

                    Base::InternalFromString(ValueStr, Verify);

                    if( Verify )
                        Base::InternalCheckError();
                }

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

        //! Checks if the value comes from cache or is requested from another node
        virtual bool IsValueCacheValid() const
        {
            return Base::InternalIsValueCacheValid();
        }

    };


} // namespace GenApi

#endif // GENAPI_VALUET_H
