//-----------------------------------------------------------------------------
//  (c) 2006-11 by Basler Vision Technologies
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
    \ingroup GenApi_Implementation
*/

#ifndef GENAPI_EXCEPTION_H
#define GENAPI_EXCEPTION_H

#include "Base/GCException.h"
#include "INodePrivate.h"

namespace GENAPI_NAMESPACE
{

    //! denotes through which method call the node tree was entered
    typedef enum
    {
        meUndefined,
        meGetAccessMode,
        meToString,
        meFromString,
        meGetValue,
        meSetValue,
        meGetMin,
        meGetMax,
        meGetInc,
        meExecute,
        meIsDone,
        meSetIntValue,
        meGetIntValue,
        meSet,
        meGet,
        meGetIncMode,
        meGetListOfValidValues
    } EMethod;

    class EMethodClass
    {
    public:
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EMethod *pValue)
        {
            assert( pValue );

            if( *pValue == meGetAccessMode )
                ValueStr = "GetAccessMode";
            else if( *pValue == meToString )
                ValueStr = "ToString";
            else if( *pValue == meFromString )
                ValueStr = "FromString";
            else if( *pValue == meGetValue )
                ValueStr = "GetValue";
            else if( *pValue == meSetValue )
                ValueStr = "SetValue";
            else if( *pValue == meGetMin )
                ValueStr = "GetMin";
            else if( *pValue == meGetMax )
                ValueStr = "GetMax";
            else if( *pValue == meGetInc )
                ValueStr = "GetInc";
            else if( *pValue == meExecute )
                ValueStr = "Execute";
            else if( *pValue == meIsDone )
                ValueStr = "IsDone";
            else if( *pValue == meSetIntValue )
                ValueStr = "SetIntValue";
            else if( *pValue == meGetIntValue )
                ValueStr = "GetIntValue";
            else if( *pValue == meSet )
                ValueStr = "Set";
            else if( *pValue == meGet )
                ValueStr = "Get";
            else
                ValueStr = "_UndefinedMethod";
        }

        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EMethod Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    GENICAM_NAMESPACE::gcstring getEntryPoint(INodeMap* nodeMap);

    template <class E>
    class ExceptionReporterNode : public GENICAM_NAMESPACE::ExceptionReporter<E>
    {
    public:
        ExceptionReporterNode( const char* sourceFileName, unsigned int sourceLine, const INodePrivate* pNodePrivate, const char* pExceptionType )
          : GENICAM_NAMESPACE::ExceptionReporter<E>( sourceFileName, sourceLine )
          , m_pNodePrivate( pNodePrivate )
          , m_ExceptionType( pExceptionType )
        { }

        E Report( const char* pFormat, ... )
        {
            using namespace GENICAM_NAMESPACE;
            // print the actual error description to pBuffer
            char pBuffer[ 256 ];
            va_list vap;
            va_start( vap, pFormat );

#if defined (_MSC_VER)
			vsnprintf_s( pBuffer, sizeof pBuffer, _TRUNCATE, pFormat, vap );
#else 
            vsnprintf( pBuffer, sizeof pBuffer, pFormat, vap );
#endif 
            va_end(vap);
            return E( pBuffer, 
                GENICAM_NAMESPACE::ExceptionReporter<E>::m_SourceFileName.c_str(), GENICAM_NAMESPACE::ExceptionReporter<E>::m_SourceLine,   
                getEntryPoint(m_pNodePrivate->GetNodeMap()).c_str(),
                m_pNodePrivate->GetName().c_str(),  
                m_ExceptionType.c_str()  
                );
        }

    private:
        // The current node
        const INodePrivate *m_pNodePrivate;

        //! The full error message
        GENICAM_NAMESPACE::gcstring m_ExceptionType;

    };

    //! Fires an exception, e.g. throw EXCEPTION("%ld too large", Value);
#   define GENERIC_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::GenericException>(__FILE__, __LINE__, this, "GenericException" ).Report

    //! Fires an invalid argument exception, e.g. throw INVALID_ARGUMENT("%ld too large", Value);
#   define INVALID_ARGUMENT_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::InvalidArgumentException>(__FILE__, __LINE__, this, "InvalidArgumentException" ).Report

    //! Fires an out of range exception, e.g. throw OUT_OF_RANGE_EXCEPTION("%ld too large", Value);
#   define OUT_OF_RANGE_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::OutOfRangeException>(__FILE__, __LINE__, this, "OutOfRangeException" ).Report

    //! Fires an property exception, e.g. throw PROPERTY_EXCEPTION("%ld too large", Value);
#   define PROPERTY_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::PropertyException>(__FILE__, __LINE__, this, "PropertyException" ).Report

    //! Fires a runtime exception, e.g. throw RUNTIME_EXCEPTION("buh!")
#   define RUNTIME_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::RuntimeException>(__FILE__, __LINE__, this, "RuntimeException" ).Report

    //! Fires a logical error exception, e.g. throw LOGICAL_ERROR_EXCEPTION("Should never reach this point")
#   define LOGICAL_ERROR_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::LogicalErrorException>(__FILE__, __LINE__, this, "LogicalErrorException" ).Report

    //! Fires a access error exception, e.g. throw ACCESS_ERROR_EXCEPTION("Not everybody")
#   define ACCESS_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::AccessException>(__FILE__, __LINE__, this, "AccessException" ).Report

    //! Fires a timeout error exception, e.g. throw TIMEOUT_EXCEPTION("Not everybody")
#   define TIMEOUT_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::TimeoutException>(__FILE__, __LINE__, this, "TimeoutException" ).Report

    //! Fires a dynamic cast exception, e.g. throw DYNAMICCAST_EXCEPTION("Not everybody")
#   define DYNAMICCAST_EXCEPTION_NODE GENAPI_NAMESPACE::ExceptionReporterNode<GENICAM_NAMESPACE::DynamicCastException>(__FILE__, __LINE__, this, "DynamicCastException" ).Report

    //! Range check for int64
#   define CHECK_RANGE_I64_NODE(_Value, _Min, _Max, _Inc) \
        if((int64_t)(_Value) < (int64_t)(_Min)) \
            throw OUT_OF_RANGE_EXCEPTION_NODE("Value = %" FMT_I64 "d must be equal or greater than Min = %" FMT_I64 "d.", (int64_t)(_Value), (int64_t)(_Min)); \
        else if((int64_t)(_Value) > (int64_t)(_Max)) \
            throw OUT_OF_RANGE_EXCEPTION_NODE("Value = %" FMT_I64 "d must be equal or smaller than Max = %" FMT_I64 "d.", (int64_t)(_Value), (int64_t)(_Max)); \
        else if ( 0 >= _Inc ) \
            throw LOGICAL_ERROR_EXCEPTION_NODE("Increment must be larger than 0."); \
        else if( ((int64_t)(_Value) - (int64_t)(_Min)) % (int64_t)(_Inc) != 0) \
            throw OUT_OF_RANGE_EXCEPTION_NODE("The difference between Value = %" FMT_I64 "d and Min = %" FMT_I64 "d must be dividable without rest by Inc = %" FMT_I64 "d.", (int64_t)(_Value), (int64_t)(_Min), (int64_t)(_Inc));

    //! Range check for float
#   define CHECK_RANGE_FLT_NODE(_Value, _Min, _Max) \
        if ((_Value) < (_Min)) \
            throw OUT_OF_RANGE_EXCEPTION_NODE( "Value %f must be greater than or equal %f.", (_Value), (_Min) ); \
        else if ((_Value) > (_Max)) \
            throw OUT_OF_RANGE_EXCEPTION_NODE( "Value %f must be smaller than or equal %f.", (_Value), (_Max) );


}

#endif // GENAPI_EXCEPTION_H

