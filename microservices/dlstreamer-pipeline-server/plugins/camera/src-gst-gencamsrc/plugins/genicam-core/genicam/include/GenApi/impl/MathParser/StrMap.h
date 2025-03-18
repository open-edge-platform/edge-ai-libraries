//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Margret Albrecht
//  $Header$
//
//  License: Derived from Kirill Zaborski's MathParser library (http://kirya.narod.ru/mathparser.html ).
//  This library comes under LGPL license (see http://www.gnu.org/licenses/lgpl.html).
//  Kirill's implementation is a C++ port of the CCalc library from Walery Studennikov (http://www.sama.ru/~despair/ccalc/)
//  which also comes under the LGPL.
//-----------------------------------------------------------------------------
/*!
\file
\brief    Definition of CStrMap
*/
#ifndef _STRMAP_H_
#define _STRMAP_H_

#include "MathParserDll.h"

/**
* \ingroup internal_impl
*
* \brief Map for variables in swissknife expression
*/
class MATHPARSERDLL_API CStrMap
{
    int   FCount, FCapacity;
    int   FExtraLen, FRecordLen;
    int   FDoDuplicate;
    char* FList;
public:
    CStrMap( int extrabytes = sizeof( double ), int dup = 0 );
    ~CStrMap( void );
    void AddString( const char* str, void* data );
    void AddStrLen( const char* str, size_t len, const void* data );
    void TrimClear( int NewCount );
    void SetCapacity( int NewCapacity );
    int LenIndexOf( const char* str, size_t len, const void** data );
    const void* DataAt( int index );
    bool IsEmpty()
    {
        return FCount == 0;
    }
};

// these must match StaticFuncMapDouble
#define FUNC_ROUND    13
#define FUNC_E        18
#define FUNC_PI        19

class MATHPARSERDLL_API CStaticFuncMapDouble
{
public:
    static int LenIndexOf( const char* str, size_t len, const void** data );
};

class MATHPARSERDLL_API CStaticFuncMapInt64
{
public:
    static int LenIndexOf( const char* str, size_t len, const void** data );
};

#endif //_STRMAP_H_
