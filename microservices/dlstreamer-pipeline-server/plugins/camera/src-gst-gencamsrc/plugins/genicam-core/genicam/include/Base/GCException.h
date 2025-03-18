//-----------------------------------------------------------------------------
//  (c) 2004 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenICam
//  Author:  Fritz Dierks
//  $Header$
//
//  01.10.2014 Stemmer, SD
//             prepared for remove of std::exception base class 
//
//  14.03.2005 Stemmer, RS
//             changed minor things like namespace
//             added a AccessException
//             added a TimeoutException
//
//  21.02.2006 Stemmer, SD
//             used _vsnprintf_s function for VS8 and higher (compiler fork)
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
    Standard GenICam Exceptions
    \ingroup Base_PublicUtilities
    */

#ifndef GENCAM_EXCEPTION_H_
#define GENCAM_EXCEPTION_H_

#include <cassert>
#include <cstdarg>
#include <exception>
#include <sstream>
#include <stdio.h>
#include <stdarg.h>
#include <Base/GCTypes.h>
#include <Base/GCString.h>

#pragma pack(push, 8)

namespace GENICAM_NAMESPACE
{
    /**
    \brief GenICam's exception class
    \ingroup Base_PublicUtilities
    */
    class GCBASE_RTTI_CLASS_API GenericException 
    {
    public:
        //! Constructor
        GenericException(const char* pDescription, const char *pSourceFileName, unsigned int SourceLine);

        //! Constructor
        GenericException(const char* pDescription, const char *pSourceFileName, unsigned int SourceLine, const char* pExceptionType);

        //! Constructor (GenApi specific)
        GenericException(const char* pDescription, const char *pSourceFileName, unsigned int SourceLine, const char *pEntryPoint, const char *pErrorNodeName, const char* pExceptionType);

        //! Get error description
        virtual const char* GetDescription() const throw();

        //! Get filename in which the error occurred
        virtual const char* GetSourceFileName() const throw();

        //! Get line number at which the error occurred
        virtual unsigned int GetSourceLine() const throw();

        //! Get error description (overwrite from std:exception)
        virtual const char *what() const throw();

        virtual ~GenericException() throw();

    private:

        //! Assembles the error message
        void AssembleMessage();

        //! The full error message
        GENICAM_NAMESPACE::gcstring m_What;

        //! The full error message
        GENICAM_NAMESPACE::gcstring m_ExceptionType;

        //! Line number at which the error occurred
        unsigned int m_SourceLine;

        //! Filename in which the error occurred
        GENICAM_NAMESPACE::gcstring m_SourceFileName;

        //! Error description
        GENICAM_NAMESPACE::gcstring m_Description;

        /* the following members are GenApi specific */

        //! Node and method where the call stack entered the node map (may be empty)
        GENICAM_NAMESPACE::gcstring m_EntryPoint;

        //! Node where the error occurred (may be empty)
        GENICAM_NAMESPACE::gcstring m_ErrorNodeName;
    };

    //! Creates an exception with the same functionality as the GenericException but being of different type
    //! \ingroup Base_PublicUtilities
#define DECLARE_EXCEPTION( name ) \
        class GCBASE_RTTI_CLASS_API name : public GENICAM_NAMESPACE::GenericException \
            { \
        public: \
            name( const char* pDescription, const char *pSourceFileName, int SourceLine ); \
            name( const char* pDescription, const char *pSourceFileName, int SourceLine, const char* pExceptionType  ); \
            name( const char* pDescription, const char *pSourceFileName, int SourceLine, const char *pEntryPoint, const char *pErrorNodeName, const char* pExceptionType ); \
            }

    //! \addtogroup Base_PublicUtilities
    
    DECLARE_EXCEPTION(BadAllocException);

    //! Exception fired if an argument is invalid
    DECLARE_EXCEPTION(InvalidArgumentException);

    //! Exception fired if an argument is out of range
    DECLARE_EXCEPTION(OutOfRangeException);

    //! Exception fired if a property access fails
    DECLARE_EXCEPTION(PropertyException);

    //! Runtime exception
    DECLARE_EXCEPTION(RuntimeException);

    //! Exception to be thrown to indicate logical errors in program flow
    DECLARE_EXCEPTION(LogicalErrorException);

    //! Exception to be thrown to indicate an access error
    DECLARE_EXCEPTION(AccessException);

    //! Exception to be thrown to indicate an timeout error
    DECLARE_EXCEPTION(TimeoutException);

    //! Exception to be thrown to indicate the result of a dynamic cast was zero
    DECLARE_EXCEPTION(DynamicCastException);

    //! \}

    /*-----------------------------------------------------------------*/
    // Utilities
    /*-----------------------------------------------------------------*/

    /**
    \brief printf like creation of exceptions
    \ingroup Base_PublicImpl
    */
    template <typename E>
    class ExceptionReporter
    {
    public:

        ExceptionReporter(const char* pSourceFileName, int SourceLine)
            : m_SourceFileName(pSourceFileName)
            , m_SourceLine(SourceLine)
        {
        }

        ExceptionReporter(const char* pSourceFileName, int SourceLine, const char* pExceptionType)
            : m_SourceFileName(pSourceFileName)
            , m_SourceLine(SourceLine)
            , m_ExceptionType(pExceptionType)
        {
        }

        E Report(const char* pFormat, ...)
        {
            char pBuffer[256];
            va_list vap;
            va_start(vap, pFormat);

#               if defined (_MSC_VER)
            vsnprintf_s(pBuffer, sizeof pBuffer, _TRUNCATE, pFormat, vap);
#               else 
            vsnprintf( pBuffer, sizeof pBuffer, pFormat, vap );
#               endif 

            va_end(vap);

            return E(pBuffer, m_SourceFileName.c_str(), m_SourceLine, m_ExceptionType.c_str());
        };

        E Report()
        {
            return E("", m_SourceFileName.c_str(), m_SourceLine, m_ExceptionType.c_str());
        }

        E Report(const std::string &s)
        {
            return E(s.c_str(), m_SourceFileName.c_str(), m_SourceLine, m_ExceptionType.c_str());
        }

        E Report(const std::stringstream& str)
        {
            return E(str.str().c_str(), m_SourceFileName.c_str(), m_SourceLine, m_ExceptionType.c_str());
        }

    protected:
        //! the path to the source file where the exception is thrown
        GENICAM_NAMESPACE::gcstring m_SourceFileName;

        //! The line within the source file where the exception is thrown
        int m_SourceLine;

        //! the type of the exception in string
        GENICAM_NAMESPACE::gcstring m_ExceptionType;
    };

    //! \addtogroup Base_PublicImpl
    //! \{

    //! Fires a generic exception, e.g. throw GENERIC_EXCEPTION("%ld too large", Value);
    #define GENERIC_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::GenericException>(__FILE__, __LINE__).Report

    //! Fires a bad alloc exception, e.g. throw BAD_ALLOC_EXCEPTION();
    #define BAD_ALLOC_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::BadAllocException>(__FILE__, __LINE__, "BadAllocException" ).Report

    //! Fires an invalid argument exception, e.g. throw INVALID_ARGUMENT_EXCEPTION("%ld too large", Value);
    #define INVALID_ARGUMENT_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::InvalidArgumentException>(__FILE__, __LINE__, "InvalidArgumentException" ).Report

    //! Fires an out of range exception, e.g. throw OUT_OF_RANGE_EXCEPTION("%ld too large", Value);
    #define OUT_OF_RANGE_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::OutOfRangeException>(__FILE__, __LINE__, "OutOfRangeException" ).Report

    //! Fires an property exception, e.g. throw PROPERTY_EXCEPTION("%ld too large", Value);
    #define PROPERTY_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::PropertyException>(__FILE__, __LINE__, "PropertyException" ).Report

    //! Fires a runtime exception, e.g. throw RUNTIME_EXCEPTION("buh!")
    #define RUNTIME_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::RuntimeException>(__FILE__, __LINE__, "RuntimeException" ).Report

    //! Fires a logical error exception, e.g. throw LOGICAL_ERROR_EXCEPTION("Should never reach this point")
    #define LOGICAL_ERROR_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::LogicalErrorException>(__FILE__,  __LINE__, "LogicalErrorException" ).Report

    //! Fires a access exception, e.g. throw ACCESS_EXCEPTION("Not everybody")
    #define ACCESS_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::AccessException>(__FILE__, __LINE__, "AccessException" ).Report

    //! Fires a timeout error exception, e.g. throw TIMEOUT_EXCEPTION("Not everybody")
    #define TIMEOUT_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::TimeoutException>(__FILE__, __LINE__,"TimeoutException" ).Report

    //! Fires a dynamic cast exception, e.g. throw DYNAMICCAST_EXCEPTION("Not everybody")
    #define DYNAMICCAST_EXCEPTION GENICAM_NAMESPACE::ExceptionReporter<GENICAM_NAMESPACE::DynamicCastException>(__FILE__, __LINE__, "DynamicCastException" ).Report

    //! Range check for int64
    #define CHECK_RANGE_I64(_Value, _Min, _Max, _Inc) \
        if((int64_t)(_Value) < (int64_t)(_Min)) \
            throw OUT_OF_RANGE_EXCEPTION("Value = %" FMT_I64 "d must be equal or greater than Min = %" FMT_I64 "d", (int64_t)(_Value), (int64_t)(_Min)); \
                else if((int64_t)(_Value) > (int64_t)(_Max)) \
            throw OUT_OF_RANGE_EXCEPTION("Value = %" FMT_I64 "d must be equal or smaller than Max = %" FMT_I64 "d", (int64_t)(_Value), (int64_t)(_Max)); \
                else if ( 0 == _Inc ) \
            throw LOGICAL_ERROR_EXCEPTION("Increment must not equal 0!"); \
                else if( ((int64_t)(_Value) - (int64_t)(_Min)) % (int64_t)(_Inc) != 0) \
            throw OUT_OF_RANGE_EXCEPTION("The difference between Value = %" FMT_I64 "d and Min = %" FMT_I64 "d must be dividable without rest by Inc = %" FMT_I64 "d", (int64_t)(_Value), (int64_t)(_Min), (int64_t)(_Inc));

    //! Range check for float
    #define CHECK_RANGE_FLT(_Value, _Min, _Max) \
        if ((_Value) < (_Min)) \
            throw OUT_OF_RANGE_EXCEPTION( "Value %f must be greater than or equal %f", (_Value), (_Min) ); \
        else if ((_Value) > (_Max)) \
            throw OUT_OF_RANGE_EXCEPTION( "Value %f must be smaller than or equal %f", (_Value), (_Max) );

    //! Checks if a dynamic_cast is possible
    #define CHECK_DYNAMIC_CAST_POINTER( _Pointer )\
        assert( (_Pointer) != NULL ); \
        if (NULL == (_Pointer)) throw LOGICAL_ERROR_EXCEPTION( "Unexpected type in dynamic cast" )

    //! \}

}

#pragma pack(pop)

#endif // GENCAM_EXCEPTION_H_
