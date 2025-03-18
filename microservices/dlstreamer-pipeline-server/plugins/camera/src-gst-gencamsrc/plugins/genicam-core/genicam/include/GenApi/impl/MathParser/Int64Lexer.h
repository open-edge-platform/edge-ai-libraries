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
\brief    Definition of CInt64Lexer
*/

#ifndef _INT64LEXER_H_
#define _INT64LEXER_H_

#include <cstdlib>

#include "GenApi/Types.h"
#include "GenApi/impl/Internal_Compatibility.h"

#include "SymTable.h"
#include "Lexer.h" // some typdefs

/**
* \ingroup internal_impl
*
* \brief Lexical analyzer for CIntSwissKnife
*/
class CInt64Lexer
{
    char* m_pSS;
    char* SS;
public:
    // input params
    int                 cssn;    // Comment Start Symbol Number. -1 if none
    const char*         ComEnd;    // End of comment
    CSymTable*          SymTable;
    const hqCharType*   CharTypeTable;

    // output params
    char*       Name;
    size_t      NameLen;
    int64_t     ExtValue;
    int64_t     IntValue;
    hqTokenType PrevTokenType;
    hqCharType  CharType;
    int         NoIntegers;

    int SetParseString( const char* str );
    hqTokenType GetNextToken( void );
    CInt64Lexer( void );
    ~CInt64Lexer( void );
    char* GetCurrentPos( void ) const;
};

#endif //_INT64LEXER_H_
