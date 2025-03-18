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
\brief    Definition of the FloatT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_FLOATT_H
#define GENAPI_FLOATT_H


#include "../NodeCallback.h"
#include "INodePrivate.h"
#include "../Synch.h"
#include "../Counter.h"
#include "Value2String.h"
#include "GenApi/impl/Log.h"
#include <limits>
#include <cmath>
#include <cstdlib>
#include <algorithm>
#include "Exception.h"
#include "AutovectorImpl.h"

#ifdef _MSC_VER
#   pragma warning( disable : 4706 ) // assignment within conditional expression
#endif

namespace GENAPI_NAMESPACE
{
    /**
    \brief Implementation of the IFloat Interface
    */
    template<class Base>
    class FloatT : public Base
    {
    public:

        //! Constructor
        FloatT< Base >() :
            Base(),
            m_ImposedMax( (std::numeric_limits<double>::max)() ),
            m_ImposedMin( -(std::numeric_limits<double>::max)() )
        {
        }

        //! Implementation of IFloat::SetValue()
        virtual void SetValue(double Value, bool Verify = true)
        {

            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());
                typename Base::EntryMethodFinalizer E( this, meSetValue );

                GCLOGINFOPUSH( Base::m_pValueLog, "SetValue( %f )...", Value );

                if( Verify )
                {
                    if( !IsWritable( this ) )
                        throw ACCESS_EXCEPTION_NODE("Node is not writable.");

                    CHECK_RANGE_FLT_NODE(Value, Base::InternalGetMin(), Base::InternalGetMax());
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

        //! Implementation of IFloat::operator=()
        virtual IFloat& operator=(double Value)
        {
            SetValue(Value);

            return *this;
        }

        /* This is a helper function used in the method ToString (see below)
           It parses a floating point number given in a buffer s and creates a correction value used for correct rounding
           
           If the number in s is given in fixed point notation like
               123.4567
           the correction is
                 0.00005
           that is it has zeros for all trailing digits of the number followed by a '5'

           In case of scientific notation like
               1.1234e-12
           the correction number is
               0.00005e-12
           that is it has zeros for all trailing digits of the number followed by a '5' plus it has 
           the same exponent as the original number.

           The use of the correction number is explained below in the method ToString

           The code is inspired from from http://www.hackchina.com/en/r/185703/ATOF.C__html
        */
        double Correction( const char *s )
        {
            // note that while parsing the parsed value is composed even if that is not necessary
            // nevertheless the code is left as is for clarification and verification purposes
            bool sign;
            char c;

            // eat white space 
            while( isspace(c = *s) )
                s++;

            // handle sign
            if ((sign = (c == '-')))
                s++;
            else if (c == '+')
                s++;

            // read digits before decimal point
            double v = 0.0;
            while( isdigit(*s) )
                v = 10.0 * v + (*s++ - '0');

            double Cor = 0.5;
            if( *s == '.' )
            {
                s++;

                // eat digits after decimal point
                double fr = 10.0;
                while( isdigit(*s) )
                {
                    v += (*s++ - '0') / fr;
                    Cor *= 0.1;
                    fr *= 10.0;
                }
            }

            // handle exponent
            double exp = 1.0;
            if (tolower(*s) == 'e')
            {
                int i = atoi(s);
                exp = pow(10.0, i);
            }

            //v *= exp;
            //v = sign ? -v : v;

            Cor *= exp;

            return Cor;
        }

        //! Get value of the node as string
        virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false)
        {
            AutoLock l(Base::GetLock());
            
            std::stringstream Buffer;
            std::ostringstream CorrectedBuffer;

            // set DisplayNotation
            switch( Base::InternalGetDisplayNotation() )
            {
            case fnAutomatic:
                // default
                break;
            case fnFixed:
                Buffer.setf(std::ios::fixed, std::ios::floatfield);
                CorrectedBuffer.setf(std::ios::fixed, std::ios::floatfield);
                break;
            case fnScientific:
                Buffer.setf(std::ios::scientific, std::ios::floatfield);
                CorrectedBuffer.setf(std::ios::scientific, std::ios::floatfield);
                break;
            #pragma BullseyeCoverage off
            default:
                assert(false);
            #pragma BullseyeCoverage on
            }

            // set DisplayPrecision
            int Precision = (int)GetDisplayPrecision();
            Buffer.precision( Precision ); 
            CorrectedBuffer.precision( Precision ); 

            // output
            double Value = GetValue( Verify, IgnoreCache );
            Buffer << Value;

            // Make sure FromString will work with the result
            // for details see the test code in FloatTestSuite::TestTicket785

            // read back the created string
            double VerifyValue;
            Buffer >> VerifyValue;

            double CorrectedValue = Value;
            bool LimitsExceeded = false;
            
            // the string may be too large due to rounding issues
            if( VerifyValue > Base::InternalGetMax() )
            {
                CorrectedValue = Value - Correction( Buffer.str().c_str() );
                LimitsExceeded = true;
            }
            else if( VerifyValue < Base::InternalGetMin() )
            {
                CorrectedValue = Value + Correction( Buffer.str().c_str() );
                LimitsExceeded = true;
            }
            
            GENICAM_NAMESPACE::gcstring valueString;
            if( LimitsExceeded )
            {
                CorrectedBuffer << CorrectedValue;
                valueString = CorrectedBuffer.str().c_str();
            }
            else
            {
                valueString = Buffer.str().c_str();
            }
            return valueString;
        }

        //! Implementation of IFloat::GetValue()
        virtual double GetValue(bool Verify = false, bool IgnoreCache = false)
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetValue, IgnoreCache );

            // Note that readability is tested regardless of Verify
            if( !IsReadable( this ) )
                throw ACCESS_EXCEPTION_NODE("Node is not readable.");

            #if ! defined( DISABLE_VALUE_CACHING ) || (DISABLE_VALUE_CACHING == 0)
                // Use cache
                if (!IgnoreCache && Base::m_ValueCacheValid && !Verify)
                {
                    GCLOGINFO( Base::m_pValueLog, "GetValue = %f  (from cache)", m_ValueCache );

                    return m_ValueCache;
                }
            #endif

            GCLOGINFOPUSH( Base::m_pValueLog, "GetValue...");

            const double Value( Base::InternalGetValue(Verify, IgnoreCache) );

            GCLOGINFOPOP( Base::m_pValueLog, "...GetValue = %f", Value );

            if( Verify )
            {
                CHECK_RANGE_FLT_NODE(Value, Base::InternalGetMin(), Base::InternalGetMax());
                Base::InternalCheckError();
            }

            #if ! defined( DISABLE_VALUE_CACHING ) || (DISABLE_VALUE_CACHING == 0)
                // Fill cache
                const ECachingMode CachingMode(static_cast<INode *>(this)->GetCachingMode());
                if(    WriteThrough == CachingMode
                    || WriteAround  == CachingMode  )
                {
                    m_ValueCache = Value;
                    Base::m_ValueCacheValid = true;                            
                }
            #endif

            return Value;

        }

        //! Implementation of IFloat::operator()()
        virtual double operator()()
        {
            return GetValue();
        }

        //! Implementation of IFloat::operator*()
        virtual double operator*()
        {
            return GetValue();
        }

        //! Set value of the node as string
        virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true)
        {
            double value;
            if (!String2Value(ValueStr,&value))
                throw INVALID_ARGUMENT_EXCEPTION_NODE("Node '%s' : cannot convert string '%s' to double.", Base::m_Name.c_str(),  ValueStr.c_str() );

            SetValue(value, Verify);
        }


        //! Implementation of IFloat::GetMin()
        virtual double GetMin()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetMin );

            // only allowed for available nodes
            if (!IsAvailable(this))
                throw ACCESS_EXCEPTION_NODE("Node is not available.");

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetMin..." );

            double Minimum = Base::InternalGetMin();
            Minimum = (std::max)(Minimum, m_ImposedMin);

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetMin = %f", Minimum );

            return Minimum;

        }

        //! Implementation of IFloat::GetMax()
        virtual double GetMax()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetMax );

            // only allowed for available nodes
            if (!IsAvailable(this))
                throw ACCESS_EXCEPTION_NODE("Node is not available.");

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetMax...");

            double Maximum(Base::InternalGetMax());
            Maximum = (std::min)( Maximum, m_ImposedMax );

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetMax = %f", Maximum );

            return Maximum;

        }

        //! True if the float has a constant increment
        virtual bool HasInc()
        {
            AutoLock l(Base::GetLock());

            GCLOGINFOPUSH( Base::m_pRangeLog, "HasInc...");

            bool HasInc( Base::InternalHasInc() );
#pragma BullseyeCoverage off
            GCLOGINFOPOP( Base::m_pRangeLog, "...HasInc = " + (HasInc ? GENICAM_NAMESPACE::gcstring("true") : GENICAM_NAMESPACE::gcstring("false")));
#pragma BullseyeCoverage on

            return HasInc;

        }

        virtual EIncMode GetIncMode()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetIncMode );

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetIncMode...");

            if( ! Base::m_ListOfValidValuesCacheValid )
            {
               m_CurentValidValueSet = Base::InternalGetListOfValidValues();
               Base::m_ListOfValidValuesCacheValid = true;
            }

            EIncMode incMode( (m_CurentValidValueSet.size())? listIncrement: Base::InternalHasInc()? fixedIncrement : noIncrement  );

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetIncMode" );

            return incMode;
        }

        //! Get the constant increment if there is any
        virtual double GetInc()
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetInc );

            if( !Base::InternalHasInc() )
                throw RUNTIME_EXCEPTION_NODE("node does not have an increment." );

            // only allowed for available nodes
            if (!IsAvailable(this))
                throw ACCESS_EXCEPTION_NODE("Node is not available.");

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetInc...");

            double Inc( Base::InternalGetInc() );

            GCLOGINFOPOP( Base::m_pRangeLog, "...GetInc = %f", Inc );

            return Inc;
        }

        //! Get list of valid value
        virtual double_autovector_t GetListOfValidValues(bool bounded = true)
        {
            AutoLock l(Base::GetLock());
            typename Base::EntryMethodFinalizer E( this, meGetListOfValidValues );

            GCLOGINFOPUSH( Base::m_pRangeLog, "GetListOfValidValues...");
            if( ! Base::m_ListOfValidValuesCacheValid )
            {
               m_CurentValidValueSet = Base::InternalGetListOfValidValues();
               Base::m_ListOfValidValuesCacheValid = true;
            }

            double_autovector_t list( ( bounded)? m_CurentValidValueSet.duplicate( Base::InternalGetMin(), Base::InternalGetMax()) : m_CurentValidValueSet);


            GCLOGINFOPOP( Base::m_pRangeLog, "...GetListOfValidValues" );
            return list;


        }


        //! Implementation of IFloat::GetRepresentation()
        virtual  ERepresentation GetRepresentation()
        {
            AutoLock l(Base::GetLock());
            return Base::InternalGetRepresentation();
        }

        //! Implementation of IFloat::GetUnit()
        virtual GENICAM_NAMESPACE::gcstring GetUnit() const
        {
            AutoLock l(Base::GetLock());
            return Base::InternalGetUnit();
        }

        //! Get the way the float should be converted to a string
        virtual EDisplayNotation GetDisplayNotation() const
        {
            AutoLock l(Base::GetLock());
            return Base::InternalGetDisplayNotation();
        }

        //! Get the DisplayPrecision to be used when converting the float to a string
        virtual int64_t GetDisplayPrecision() const
        {
            AutoLock l(Base::GetLock());

            int64_t Precision = Base::InternalGetDisplayPrecision();

            if( Precision == -1 )
            {
                // determine built in precision
                std::stringstream Buffer;
                switch( Base::InternalGetDisplayNotation() )
                {
                case fnFixed:
                    Buffer.setf(std::ios::fixed, std::ios::floatfield);
                    break;
                case fnScientific:
                    Buffer.setf(std::ios::scientific, std::ios::floatfield);
                    break;
                case fnAutomatic:
                    // default
                    break;
            #pragma BullseyeCoverage off
                default:
                    assert(false);
            #pragma BullseyeCoverage on
                 }

                Precision = Buffer.precision();
            }

            return Precision;
        }

        //! Restrict minimum value
        virtual void ImposeMin(double Value)
        {
            m_ImposedMin = Value;
            Base::SetInvalid(INodePrivate::simAll);
        }

        //! Restrict maximum value
        virtual void ImposeMax(double Value)
        {
            m_ImposedMax = Value;
            Base::SetInvalid(INodePrivate::simAll);
        }

    protected:
        //! The cache for the float value
        double m_ValueCache;

        //! a Value imposed to the maximum
        double m_ImposedMax;

        //! a Value imposed to the minimum
        double m_ImposedMin;

        //! The cached list of valie value for the integer.
        double_autovector_impl m_CurentValidValueSet;
    };
}

#endif // GENAPI_FLOATT_H
