//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Margret Albrecht
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
\brief    Definition of enum classes for Sign, Endianess, Access mode and Visibility
*/

#ifndef GENAPI_ENUMCLASSES_H
#define GENAPI_ENUMCLASSES_H
#include <GenApi/Types.h>

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // Build in enummeration classes
    //*************************************************************

    //! ESignClass holds conversion methods for the sign enumeration

    class GENAPI_DECL ESignClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, ESign *pValue)
        {
            if (!pValue) return false;
            if( ValueStr == "Signed" )
                *pValue = Signed;
            else if( ValueStr == "Unsigned" )
                *pValue = Unsigned;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, ESign *pValue)
        {

            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == Signed )
                ValueStr = "Signed";
            else if( *pValue == Unsigned )
                ValueStr = "Unsigned";
            else
                ValueStr = "_UndefinedSign";
        }

        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(ESign Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief EEndianessClass holds conversion methods for the endianess enumeration
    */
    class GENAPI_DECL EEndianessClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EEndianess *pValue)
        {
            if (!pValue) return false;
            if( ValueStr == "BigEndian" )
                *pValue = BigEndian;
            else if( ValueStr == "LittleEndian" )
                *pValue = LittleEndian;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EEndianess *pValue)
        {

            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == BigEndian )
                ValueStr = "BigEndian";
            else if( *pValue == LittleEndian )
                ValueStr = "LittleEndian";
            else
                ValueStr = "_UndefinedEndian";
        }

        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EEndianess Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief ERepresentationClass holds conversion methods for the representation enumeration
    */
    class GENAPI_DECL ERepresentationClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, ERepresentation *pValue)
        {
            if (!pValue) return false;
            if( ValueStr == "Linear" )
                *pValue = Linear;
            else if( ValueStr == "Logarithmic" )
                *pValue = Logarithmic;
            else if( ValueStr == "Boolean" )
                *pValue = Boolean;
            else if( ValueStr == "PureNumber" )
                *pValue = PureNumber;
            else if( ValueStr == "HexNumber" )
                *pValue = HexNumber;
            else if( ValueStr == "IPV4Address" )
                *pValue = IPV4Address;
            else if( ValueStr == "MACAddress" )
                *pValue = MACAddress;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, ERepresentation *pValue)
        {
            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == Linear )
                ValueStr = "Linear";
            else if( *pValue == Logarithmic )
                ValueStr = "Logarithmic";
            else if( *pValue == Boolean )
                ValueStr = "Boolean";
            else if( *pValue == PureNumber )
                ValueStr = "PureNumber";
            else if( *pValue == HexNumber )
                ValueStr = "HexNumber";
            else if( *pValue == IPV4Address )
                ValueStr = "IPV4Address";
            else if( *pValue == MACAddress )
                ValueStr = "MACAddress";
            else
                ValueStr = "_UndefinedRepresentation";
        }

        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(ERepresentation Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief EVisibilityClass holds conversion methods for the visibility enumeration
    */
    class GENAPI_DECL EVisibilityClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EVisibility *pValue)
        {
            if (!pValue) return false;
            if( ValueStr == "Beginner" )
                *pValue = Beginner;
            else if( ValueStr == "Expert" )
                *pValue = Expert;
            else if( ValueStr == "Guru" )
                *pValue = Guru;
            else if( ValueStr == "Invisible" )
                *pValue = Invisible;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EVisibility *pValue)
        {
            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == Beginner )
                ValueStr = "Beginner";
            else if( *pValue == Expert )
                ValueStr = "Expert";
            else if( *pValue == Guru )
                ValueStr = "Guru";
            else if( *pValue == Invisible )
                ValueStr = "Invisible";
            else
                ValueStr = "_UndefinedVisibility";
        }
        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EVisibility Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief EAccessModeClass holds conversion methods for the access mode enumeration
    */
    class GENAPI_DECL EAccessModeClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EAccessMode *pValue)
        {

            if (!pValue) return false;
            if( ValueStr == "RW" )
                *pValue = RW;
            else if( ValueStr == "RO" )
                *pValue = RO;
            else if( ValueStr == "WO" )
                *pValue = WO;
            else if( ValueStr == "NA" )
                *pValue = NA;
            else if( ValueStr == "NI" )
                *pValue = NI;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EAccessMode *pValue)
        {
            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == RW )
                ValueStr = "RW";
            else if( *pValue == RO )
                ValueStr = "RO";
            else if( *pValue == WO )
                ValueStr = "WO";
            else if( *pValue == NI )
                ValueStr = "NI";
            else if( *pValue == NA )
                ValueStr = "NA";
            else
                ValueStr = "_UndefinedAccessMode";
        }

        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EAccessMode Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief ECachingModeClass holds conversion methods for the caching mode enumeration
    */
  class GENAPI_DECL ECachingModeClass
  {
  public:
    //! Converts a string to enum value
    static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, ECachingMode *pValue )
    {
      if( ! pValue ) return false;
      if( ValueStr == "NoCache" )
        *pValue = NoCache;
      else if( ValueStr == "WriteThrough" )
        *pValue = WriteThrough;
      else if( ValueStr == "WriteAround" )
        *pValue = WriteAround;
      else
        return false;
      return true;
    }
    static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, ECachingMode *pValue)
    {
      if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
      if( *pValue == NoCache )
        ValueStr = "NoCache";
      else if( *pValue == WriteThrough )
        ValueStr = "WriteThrough";
      else if( *pValue == WriteAround )
        ValueStr = "WriteAround";
      else
        ValueStr = "_UndefinedCachingMode";
    }
        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(ECachingMode Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }

  };

    /**
    \brief Holds conversion methods for the namespace enumeration
    */
    class GENAPI_DECL ENameSpaceClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, ENameSpace *pValue)
        {
            if (!pValue) return false;
            if( ValueStr == "Custom" )
                *pValue = Custom;
            else if( ValueStr == "Standard" )
                *pValue = Standard;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, ENameSpace *pValue)
        {
            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == Custom )
                ValueStr = "Custom";
            else if( *pValue == Standard )
                ValueStr = "Standard";
            else
                ValueStr = "_UndefinedNameSpace";
        }
        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(ENameSpace Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief Holds conversion methods for the standard namespace enumeration
    */
    class GENAPI_DECL EYesNoClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EYesNo *pValue)
        {
            if (!pValue) return false;
            if( ValueStr == "Yes" )
                *pValue = Yes;
            else if( ValueStr == "No" )
                *pValue = No;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EYesNo *pValue)
        {
            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == Yes)
                ValueStr = "Yes";
            else if( *pValue == No )
                ValueStr = "No";
            else
                ValueStr = "_UndefinedYesNo";
        }

        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EYesNo Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief Holds conversion methods for the standard namespace enumeration
    */
    class GENAPI_DECL EStandardNameSpaceClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EStandardNameSpace *pValue)
        {
            if (!pValue) return false;
            if( ValueStr == "None" )
                *pValue = None;
            else if( ValueStr == "GEV" )
                *pValue = GEV;
            else if( ValueStr == "IIDC" )
                *pValue = IIDC;
            else if( ValueStr == "CL" )
                *pValue = CL;
            else if( ValueStr == "USB" )
                *pValue = USB;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EStandardNameSpace *pValue)
        {
            if( ! pValue ) throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );
            if( *pValue == None )
                ValueStr = "None";
            else if( *pValue == GEV )
                ValueStr = "GEV";
            else if( *pValue == IIDC )
                ValueStr = "IIDC";
            else if( *pValue == CL )
                ValueStr = "CL";
            else if( *pValue == USB )
                ValueStr = "USB";
            else
                ValueStr = "_UndefinedStandardNameSpace";
        }
        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EStandardNameSpace Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief Holds conversion methods for the converter formulas
    */
    class GENAPI_DECL ESlopeClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, ESlope *pValue)
        {
            if (!pValue)
                return false;

            if( ValueStr == "Increasing" )
                *pValue = Increasing;
            else if( ValueStr == "Decreasing" )
                *pValue = Decreasing;
            else if( ValueStr == "Varying" )
                *pValue = Varying;
            else if( ValueStr == "Automatic" )
                *pValue = Automatic;
            else
                return false;

            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, ESlope *pValue)
        {
            if( ! pValue )
                throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );

            if( *pValue == Increasing )
                ValueStr = "Increasing";
            else if( *pValue == Decreasing )
                ValueStr = "Decreasing";
            else if( *pValue == Varying )
                ValueStr = "Varying";
            else if( *pValue == Automatic )
                ValueStr = "Automatic";
            else
                ValueStr = "_UndefinedESlope";
        }
        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(ESlope Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief Holds conversion methods for the notation type of floats
    */
    class GENAPI_DECL EDisplayNotationClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EDisplayNotation *pValue)
        {
            if (!pValue)
                return false;

            if( ValueStr == "Automatic" )
                *pValue = fnAutomatic;
            else if( ValueStr == "Fixed" )
                *pValue = fnFixed;
            else if( ValueStr == "Scientific" )
                *pValue = fnScientific;
            else
                return false;

            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EDisplayNotation *pValue)
        {
            if( ! pValue )
                throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );

            if( *pValue == fnAutomatic )
                ValueStr = "Automatic";
            else if( *pValue == fnFixed )
                ValueStr = "Fixed";
            else if( *pValue == fnScientific )
                ValueStr = "Scientific";
            else
                ValueStr = "_UndefinedEDisplayNotation";
        }
        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EDisplayNotation Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    /**
    \brief Holds conversion methods for the notation type of floats
    */
    class GENAPI_DECL EInputDirectionClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EInputDirection *pValue)
        {
            if (!pValue)
                return false;

            if( ValueStr == "From" )
                *pValue = idFrom;
            else if( ValueStr == "To" )
                *pValue = idTo;
            else if( ValueStr == "None" )
                *pValue = idNone;
            else
                return false;

            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EInputDirection *pValue)
        {
            if( ! pValue )
                throw INVALID_ARGUMENT_EXCEPTION( "NULL argument pValue" );

            if( *pValue == idFrom )
                ValueStr = "From";
            else if( *pValue == idTo )
                ValueStr = "To";
            else if( *pValue == idNone )
                ValueStr = "None";
            else
                ValueStr = "_UndefinedEInputDirection";
        }
        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EInputDirection Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };

    //! helper class converting EGenApiSchemaVersion from and to string
    class GENAPI_DECL EGenApiSchemaVersionClass
    {
    public:
        //! Converts a string to enum value
        static bool FromString(const GENICAM_NAMESPACE::gcstring &ValueStr, EGenApiSchemaVersion *pValue)
        {
            if (!pValue) return false;
            if (ValueStr == "v1_0")
                *pValue = v1_0;
            else if (ValueStr == "v1_1")
                *pValue = v1_1;
            else
                return false;
            return true;
        }
        //! Converts a string to an int32_t property
        static void ToString(GENICAM_NAMESPACE::gcstring &ValueStr, EGenApiSchemaVersion *pValue)
        {

            assert(!pValue);
            if (*pValue == v1_0)
                ValueStr = "v1_0";
            else if (*pValue == v1_1)
                ValueStr = "v1_1";
            else
                ValueStr = "_Undefined";
        }

        //! Converts a string to an int32_t property
        static GENICAM_NAMESPACE::gcstring ToString(EGenApiSchemaVersion Value)
        {
            GENICAM_NAMESPACE::gcstring Result;
            ToString(Result, &Value);
            return Result;
        }
    };


}

#endif // ifndef GENAPI_ENUMCLASSES_H
