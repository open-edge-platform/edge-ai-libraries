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
\brief    Definition of CommandT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_COMMANDT_H
#define GENAPI_COMMANDT_H

#include "GenApi/impl/Log.h"
#include "GenApi/impl/INodeMapPrivate.h"
#include "Exception.h"


namespace GENAPI_NAMESPACE
{

    /**
        \brief Implementation of the ICommand interface
    */
    template <class Base>
    class CommandT : public Base
    {
    public:
        //! Execute the command
        virtual void Execute(bool Verify = true)
        {
            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());
                typename Base::EntryMethodFinalizer E( this, meExecute );

                GCLOGINFOPUSH( Base::m_pValueLog, "Execute...");

                if( Verify && !IsWritable( this ) )
                    throw ACCESS_EXCEPTION_NODE("Node is not writable.");

                {
                    typename Base::PostSetValueFinalizer PostSetValueCaller(this, CallbacksToFire);  // dtor calls Base::PostSetValue

                    Base::PreSetValue(); // invalidates all nodes if this is the first call in a chain of SetValue-like calls

                    Base::InternalExecute(Verify);

                    if( Verify )
                        Base::InternalCheckError();

                }

                GCLOGINFOPOP( Base::m_pValueLog, "...Execute" );

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

        //! Execute the command
        virtual void operator()()
        {
            Execute();
        }

        //! Query whether the command is executed
        virtual bool IsDone(bool Verify = true)
        {
            typename Base::EntryMethodFinalizer E( this, meIsDone );

            bool Result = false;
            bool FireCallbacks = false;


            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());

                GCLOGINFOPUSH( Base::m_pValueLog, "IsDone...");

                // Note that this test runs independently of the Verify flag
                // the tests on readability/writeability are done later in the implementation
                if( !IsImplemented( this ) )
                    throw ACCESS_EXCEPTION_NODE("Node is not implemented.");

                Result = Base::InternalIsDone(Verify, FireCallbacks); 
                // InternalCheckError is already performed by InternalIsDone


                // IsDone is always called directly by the client to we do not need to deal with the bathometer here
                if(FireCallbacks)
                {
                    for ( NodePrivateVector_t::iterator it = Base::m_AllTerminalNodes.begin(); it != Base::m_AllTerminalNodes.end(); ++it )
                    {
                        (*it)->CollectCallbacksToFire(CallbacksToFire, true);
                        DeleteDoubleCallbacks(CallbacksToFire);
                        (*it)->SetInvalid(INodePrivate::simAll);
                    }
                }

#pragma BullseyeCoverage off
                GCLOGINFOPOP( Base::m_pValueLog, "...IsDone = " + (Result ? GENICAM_NAMESPACE::gcstring("true") : GENICAM_NAMESPACE::gcstring("false") ) );
#pragma BullseyeCoverage on

                // fire callbacks inside the lock
                if(FireCallbacks)
                {
                    std::list<CNodeCallback*>::iterator ptrCallback;
                    for( ptrCallback = CallbacksToFire.begin(); ptrCallback != CallbacksToFire.end(); ptrCallback++ )
                    {
                        (*ptrCallback)->operator ()(cbPostInsideLock);
                    }
                }
            }

            // fire callbacks outside the lock
            if(FireCallbacks)
            {
                std::list<CNodeCallback*>::iterator ptrCallback;
                for( ptrCallback = CallbacksToFire.begin(); ptrCallback != CallbacksToFire.end(); ptrCallback++ )
                {
                    (*ptrCallback)->operator ()(cbPostOutsideLock);
                }
            }

            return Result;
        }

    };

}

#endif
