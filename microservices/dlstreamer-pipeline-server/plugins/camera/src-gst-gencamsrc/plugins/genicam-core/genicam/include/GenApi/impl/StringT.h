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
\brief    Definition of the NodeT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_STRINGT_H
#define GENAPI_STRINGT_H

#include "../IString.h"
#include "GenApi/Compatibility.h"
#include "GenApi/impl/Log.h"
#include "Exception.h"

namespace GENAPI_NAMESPACE
{

    /**
    \brief Implementation of the IString interface
    */
    template< class Base >
    class StringT : public Base
    {
    public:
        //! Set node value
        virtual void SetValue(const GENICAM_NAMESPACE::gcstring& Value, bool Verify = true)
        {
            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());
                typename Base::EntryMethodFinalizer E( this, meSetValue );

                GCLOGINFOPUSH( Base::m_pValueLog, "SetValue( '%s' )...", Value.c_str() );

                if( Verify && !IsWritable( this ) )
                    throw  ACCESS_EXCEPTION_NODE("Node is not writable");

                {
                    typename Base::PostSetValueFinalizer PostSetValueCaller(this, CallbacksToFire);  // dtor calls Base::PostSetValue

                    Base::PreSetValue(); // invalidates all nodes if this is the first call in a chain of SetValue calls

                    Base::InternalSetValue(Value, Verify);

                    if( Verify )
                        Base::InternalCheckError();

                    // now Base::PostSetValue is called by ~PostSetValueFinalizer, i.e. updates are fired
                    // if this is the call on the top of a chain of SetValue calls
                }

                GCLOGINFOPOP( Base::m_pValueLog, "...SetValue" );

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

        //! Set node value
        virtual IString& operator=(const GENICAM_NAMESPACE::gcstring& Value)
        {
            SetValue(Value);
            return *this;
        }

        //! Get node value
        virtual GENICAM_NAMESPACE::gcstring GetValue(bool Verify = false, bool IgnoreCache = false)
        {
            AutoLock l(Base::GetLock());

            GCLOGINFOPUSH( Base::m_pValueLog, "GetValue...");

            // Note that readability is tested regardless of Verify
            if( !IsReadable( this ) )
                throw ACCESS_EXCEPTION_NODE("Node is not readable");

            GENICAM_NAMESPACE::gcstring ValueStr( Base::InternalGetValue(Verify, IgnoreCache) );

            if( Verify )
                Base::InternalCheckError();

            GCLOGINFOPOP( Base::m_pValueLog, "...GetValue = %s", ValueStr.c_str() );

            return ValueStr;

        }

        //! Get node value
        virtual GENICAM_NAMESPACE::gcstring operator()()
        {
            return GetValue();
        }

        //! Get node value
        virtual GENICAM_NAMESPACE::gcstring operator*()
        {
            return GetValue();
        }

        //! Retrieves the maximum length of the string in bytes
        virtual int64_t GetMaxLength()
        {
            AutoLock l(Base::GetLock());

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetMaxLength...");

            int64_t MaxLength = IsWritable( this ) ?
                Base::InternalGetMaxLength() 
                :
                Base::InternalGetValue().size();

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetMaxLength = %" FMT_I64 "d", MaxLength );

            return MaxLength;
        }
    
    };

}

#endif // GENAPI_STRINGT_H
