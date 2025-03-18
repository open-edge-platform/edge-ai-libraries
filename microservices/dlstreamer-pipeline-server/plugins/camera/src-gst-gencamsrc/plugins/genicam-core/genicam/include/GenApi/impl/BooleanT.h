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
\brief    Definition of BooleanT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_BOOLEANT_H
#define GENAPI_BOOLEANT_H

#include "../IBoolean.h"
#include "GenApi/impl/Log.h"
#include "Exception.h"

namespace GENAPI_NAMESPACE
{

    /**
        \brief Implementation of the IBoolean interface
    */
    template <class Base>
    class BooleanT : public Base
    {
    public:

        //! \name GenApi::IBoolean implementation
        //{
        //! IBoolean::SetValue()
        virtual void SetValue(bool Value, bool Verify = true)
        {
            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());
                typename Base::EntryMethodFinalizer E( this, meSetValue );

                if( Verify && !IsWritable( this ) )
                    throw ACCESS_EXCEPTION_NODE("Node is not writable.");
#pragma BullseyeCoverage off
                GCLOGINFOPUSH( Base::m_pValueLog, "SetValue( " + (Value ? GENICAM_NAMESPACE::gcstring("true") : GENICAM_NAMESPACE::gcstring("false")) + " )..." );
#pragma BullseyeCoverage on
                {
                    typename Base::PostSetValueFinalizer PostSetValueCaller(this, CallbacksToFire);  // dtor calls Base::PostSetValue

                    Base::PreSetValue(); // invalidates all nodes if this is the first call in a chain of SetValue calls

                    Base::InternalSetValue( Value, Verify );

                    if( Verify )
                        Base::InternalCheckError();

                }

#pragma BullseyeCoverage off
                GCLOGINFOPOP( Base::m_pValueLog, "...SetValue" );
#pragma BullseyeCoverage on

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

        //! IBoolean::operator=()
        virtual void operator=(bool Value)
        {
            SetValue( Value );
        }

        //! IBoolean::GetValue()
        virtual bool GetValue(bool Verify = false, bool IgnoreCache = false) const
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetValue, IgnoreCache );

            GCLOGINFOPUSH( Base::m_pValueLog, "GetValue..." );

            // Note that readability is tested regardless of Verify
            if( !IsReadable( this ) )
                throw ACCESS_EXCEPTION_NODE("Node is not readable.");

            const bool Value( Base::InternalGetValue(Verify, IgnoreCache) );

            if( Verify )
                Base::InternalCheckError();

            GCLOGINFOPOP( Base::m_pValueLog, "...GetValue = " + (Value ? GENICAM_NAMESPACE::gcstring("true") : GENICAM_NAMESPACE::gcstring("false") ) );

            return Value;

        }

        //! IBoolean::operator()()
        virtual bool operator()() const
        {
            return GetValue();
        }
        //}

    };
}

#endif // ifndef GENAPI_BOOLEANT_H
