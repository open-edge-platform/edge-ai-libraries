//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
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
\brief    Definition of value2string and string2value functions
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_VALUE2STRING_H
#define GENAPI_VALUE2STRING_H

#include <sstream>
#include <cctype>
#include <iomanip>

#include "Base/GCBase.h"
#include "../GenApiDll.h"
#include "PolyReference.h"
#include "Internal_Compatibility.h"


namespace GENAPI_NAMESPACE
{
    //! Dump a value container into a string
    template< typename T >
    void Values2String(const T & Values, GENICAM_NAMESPACE::gcstring &ValueStr)
    {
        std::ostringstream s;
        typename T::const_iterator it(Values.begin());
        if (it != Values.end())
            s << *it++;
        while (it != Values.end())
            s  << "\t" << *it++ ;

        ValueStr = s.str().c_str();
    }

    //! Converts an T property to a string
    template< typename T >
    void Value2String(T Value, GENICAM_NAMESPACE::gcstring &ValueStr)
    {
        static const int precision(36);  // For the MS STL, values > 36 ( == _MAX_SIG_DIG ) are leading to trailing zeroes
        std::ostringstream s;
        s << std::setprecision( precision ) << Value;
        ValueStr = s.str().c_str();
    }

    //! Converts a string to an T property
    template< typename T >
    bool String2Value(const GENICAM_NAMESPACE::gcstring &ValueStr, T* Value)
    {
        std::istringstream s(ValueStr.c_str());
        if(    ValueStr.length() > 2
            && (ValueStr[0] == '0' && (ValueStr[1] == 'x' || ValueStr[1] == 'X') ))
        {
            s.ignore( 2 );
            s >> std::hex >> *Value;
        }
        else
            s >> *Value;

        return !s.fail();
    }

    //! Converts a string to an int64_t property taking representation hints
    GENAPI_DECL bool String2Value(const char* ValueStr, int64_t* Value, ERepresentation Representation = PureNumber);

    //! Converts an int64_t property to a string taking representation hints
    GENAPI_DECL void Value2String(int64_t Value, GENICAM_NAMESPACE::gcstring &ValueStr, ERepresentation Representation = PureNumber);

    //! Converts a CIntegerPolyRef to a string
    GENAPI_DECL void Value2String(CIntegerPolyRef Value, GENICAM_NAMESPACE::gcstring &ValueStr);

    //! Converts a string to a CIntegerPolyRef
    GENAPI_DECL bool String2Value(const GENICAM_NAMESPACE::gcstring &ValueStr, CIntegerPolyRef* Value);

    //! Converts a CBooleanPolyRef to a string
    GENAPI_DECL void Value2String(CBooleanPolyRef Value, GENICAM_NAMESPACE::gcstring &ValueStr);

    //! Converts a string to a CBooleanPolyRef
    GENAPI_DECL bool String2Value(const GENICAM_NAMESPACE::gcstring &ValueStr, CBooleanPolyRef* Value);

    //! Converts a CFloatPolyRef to a string
    GENAPI_DECL void Value2String(CFloatPolyRef Value, GENICAM_NAMESPACE::gcstring &ValueStr);

    //! Converts a string to a CFloatPolyRef
    GENAPI_DECL bool String2Value(const GENICAM_NAMESPACE::gcstring &ValueStr, CFloatPolyRef* Value);

    //! Converts a CStringPolyRef to a string
    GENAPI_DECL void Value2String(CStringPolyRef Value, GENICAM_NAMESPACE::gcstring &ValueStr);

    //! Converts a string to a CStringPolyRef
    GENAPI_DECL bool String2Value(const GENICAM_NAMESPACE::gcstring &ValueStr, CStringPolyRef* Value);

    //! Converts a string to a GUID property
    GENAPI_DECL bool String2Value(const GENICAM_NAMESPACE::gcstring &ValueStr, GUID* Value);

    //! Converts a GUID property tp a string
    GENAPI_DECL void Value2String(const GUID &Value, GENICAM_NAMESPACE::gcstring &ValueStr);

    //! Converts a byte array property to a string
    GENAPI_DECL void Value2String(uint8_t *pValue, GENICAM_NAMESPACE::gcstring &ValueStr, int64_t len);

    //! Converts a string to a byte array
    GENAPI_DECL bool String2Value(const GENICAM_NAMESPACE::gcstring &ValueStr, uint8_t *pValue, int64_t len);

    //! Converts a string to a bool value
    GENAPI_DECL bool String2Value( const GENICAM_NAMESPACE::gcstring &ValueStr, bool* pValue );

    //! Converts an ASCII hex digit to a char value
    #pragma BullseyeCoverage off
    inline char Hex2Byte(uint8_t Hex)
    {
        if( 0x30 <= Hex && Hex <= 0x39 )
            return Hex - 0x30;
        else if( 0x41 <= Hex && Hex <= 0x46 )
            return Hex - 0x41 + 0x0a;
        else if( 0x61 <= Hex && Hex <= 0x66 )
            return Hex - 0x61 + 0x0a;
        else
        {
            assert(false && "if you are here its not an ASCII digit");
            return '0';
        }
    }
    #pragma BullseyeCoverage on



}
#endif // ifndef GENAPI_VALUE2STRING_H
