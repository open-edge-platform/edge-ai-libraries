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
\brief    Definition of the IntegerT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_INTEGERT_H
#define GENAPI_INTEGERT_H

#include "../Compatibility.h"
#include "../IInteger.h"
#include "Exception.h"
#include <algorithm>
#include "GenApi/impl/Log.h"
#include "AutovectorImpl.h"


namespace GENAPI_NAMESPACE
{

    /**
    \brief Implementation of the IInteger Interface
    */
    template <class Base>
    class IntegerT
        : public Base
    {
    public:

        //! Constructor
        IntegerT< Base >() :
            m_ImposedMax( GC_INT64_MAX ),
            m_ImposedMin( GC_INT64_MIN )
        {
        }

        //! Implementation of IInteger::SetValue
        virtual void SetValue(int64_t Value, bool Verify = true)
        {                        
            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());
                typename Base::EntryMethodFinalizer E( this, meSetValue );

                Base::m_ValueCacheValid = false;

                GCLOGINFOPUSH( Base::m_pValueLog, "SetValue( %" FMT_I64 "d )...", Value );

                if( Verify )
                {
                    if( !IsWritable( this ) )
                        throw ACCESS_EXCEPTION_NODE("Node is not writable.");

                    CHECK_RANGE_I64_NODE( Value, Base::InternalGetMin(), Base::InternalGetMax(), Base::InternalGetInc() );
                }

                {
                    typename Base::PostSetValueFinalizer PostSetValueCaller(this, CallbacksToFire);  // dtor calls Base::PostSetValue

                    // invalidates all nodes if this is the first call in a chain of SetValue calls
                    Base::PreSetValue();

                    // sets the value
                    Base::InternalSetValue(Value, Verify);

                    if( Verify )
                        Base::InternalCheckError();

                    #if ! defined( DISABLE_VALUE_CACHING ) || (DISABLE_VALUE_CACHING == 0)
                        // Fill cache
                        if( WriteThrough == static_cast<INode *>(this)->GetCachingMode() )
                        {
                            m_ValueCache = Value;
                            Base::m_ValueCacheValid = true;
                            Base::m_DontDeleteThisCache = true;
                        }
                    #endif

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

        //! Implementation of IInteger::operator=()
        virtual IInteger& operator=(int64_t Value)
        {
            SetValue(Value);
            return *this;
        }

        void InternalFromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true)
        {
            int64_t Value;
            if (!String2Value(ValueStr, &Value, Base::InternalGetRepresentation()))
                throw INVALID_ARGUMENT_EXCEPTION_NODE("Node '%s' : cannot convert string '%s' to int.", Base::m_Name.c_str(),  ValueStr.c_str() );

            SetValue(Value, Verify);
        }

        //! Implementation of IInteger::GetValue()
        virtual int64_t GetValue(bool Verify = false, bool IgnoreCache = false )
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetValue, IgnoreCache );

            // Note that readability is tested regardless of Verify
            if( !IsReadable( this ) )
                throw ACCESS_EXCEPTION_NODE("Node is not readable.");

            #if ! defined( DISABLE_VALUE_CACHING ) || (DISABLE_VALUE_CACHING == 0)
                // Use cache
                if ( !IgnoreCache && Base::m_ValueCacheValid && !Verify)
                {
                    GCLOGINFO( Base::m_pValueLog, "GetValue = %" FMT_I64 "d  (from cache)", m_ValueCache );
                    return m_ValueCache;
                }
            #endif

            GCLOGINFOPUSH( Base::m_pValueLog, "GetValue...");

            const int64_t Value( Base::InternalGetValue( Verify, IgnoreCache ) );

            if( Verify )
            {
                CHECK_RANGE_I64_NODE( Value, Base::InternalGetMin(), Base::InternalGetMax(), Base::InternalGetInc() );
                Base::InternalCheckError();
            }

            #if ! defined( DISABLE_VALUE_CACHING ) || (DISABLE_VALUE_CACHING == 0)
                // Fill cache
                const ECachingMode
                    CachingMode(static_cast<INode *>(this)->GetCachingMode());
                if(    WriteThrough == CachingMode
                    || WriteAround  == CachingMode  )
                {
                    m_ValueCache = Value;
                    Base::m_ValueCacheValid = true;
                }
            #endif

            GCLOGINFOPOP( Base::m_pValueLog, "...GetValue = %" FMT_I64 "d", Value );

            return Value;
        }

        //! Implementation of IInteger::operator()()
        virtual int64_t operator()()
        {
            return GetValue();
        }

        //! Implementation of IInteger::operator*()
        virtual int64_t operator*()
        {
            return GetValue();
        }

        GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false)
        {
            int64_t Value = GetValue(Verify, IgnoreCache);

            GENICAM_NAMESPACE::gcstring ValueStr;
            Value2String(Value, ValueStr, Base::InternalGetRepresentation() );

            return ValueStr;
        }

        //! Implementation of IInteger::GetMin()
        virtual int64_t GetMin()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer( this, meGetMin );

            // only allowed for available nodes
            if (!IsAvailable(this))
                throw ACCESS_EXCEPTION_NODE("Node is not available.");

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetMin...");

            int64_t Minimum = Base::InternalGetMin();
            Minimum = (std::max)(Minimum, m_ImposedMin);

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetMin = %" FMT_I64 "d", Minimum );

            return Minimum;

        }

        //! Implementation of IInteger::GetMax()
        virtual int64_t GetMax()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer( this, meGetMax );

            // only allowed for available nodes
            if (!IsAvailable(this))
                throw ACCESS_EXCEPTION_NODE("Node is not available.");

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetMax...");

            int64_t Maximum = Base::InternalGetMax();
            Maximum = (std::min)( Maximum, m_ImposedMax );

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetMax = %" FMT_I64 "d", Maximum );

            return Maximum;
        }
        //! Implementation of IInteger::GetIncMode
        virtual EIncMode GetIncMode()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer( this, meGetIncMode );

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetIncMode...");

            if( ! Base::m_ListOfValidValuesCacheValid )
            {
               m_CurentValidValueSet = Base::InternalGetListOfValidValues();
               Base::m_ListOfValidValuesCacheValid = true;
            }

            EIncMode mode( (m_CurentValidValueSet.size())? listIncrement: fixedIncrement  );

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetIncMode");
            return mode;
        }

        //! Implementation of IInteger::GetInc()
        virtual int64_t GetInc()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer( this, meGetInc );

            // only allowed for available nodes
            if( !IsAvailable(this))
                throw ACCESS_EXCEPTION_NODE("Node is not available.");

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetInc...");

            const int64_t Increment(Base::InternalGetInc());

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetInc = %" FMT_I64 "d", Increment );

            return Increment;
        }
        //! Implementation of IInteger::GetListOfValidValues
        virtual int64_autovector_t GetListOfValidValues(bool bounded = true)
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer( this, meGetListOfValidValues );
            GCLOGINFOPUSH( Base::m_pRangeLog, "GetListOfValidValues...");

            if( ! Base::m_ListOfValidValuesCacheValid )
            {
               m_CurentValidValueSet = Base::InternalGetListOfValidValues();
               Base::m_ListOfValidValuesCacheValid = true;
            }

            int64_autovector_t list( bounded? m_CurentValidValueSet.duplicate( Base::InternalGetMin(), Base::InternalGetMax()) : m_CurentValidValueSet);

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetListOfValidValues");

            return list;

        }


        //! Implementation of IInteger::GetRepresentation
        virtual  ERepresentation GetRepresentation()
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetRepresentation();
        }

        //! Implementation of IInteger::GetUnit()
        virtual GENICAM_NAMESPACE::gcstring GetUnit()
        {
            AutoLock l(Base::GetLock());
            return Base::InternalGetUnit();
        }

        //! Restrict minimum value
        virtual void ImposeMin(int64_t Value)
        {
            m_ImposedMin = Value;
            Base::SetInvalid(INodePrivate::simAll);
        }

        //! Restrict maximum value
        virtual void ImposeMax(int64_t Value)
        {
            m_ImposedMax = Value;
            Base::SetInvalid(INodePrivate::simAll);

        }

        protected:
            //! The cache for the integer value
            int64_t m_ValueCache;

            //! a Value imposed to the maximum
            int64_t m_ImposedMax;

            //! a Value imposed to the minimum
            int64_t m_ImposedMin;

            //! The cached list of valie value for the integer.
            int64_autovector_impl m_CurentValidValueSet;

    };

} // namespace GenApi

#endif
