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
\brief    Implementation of CSymTable
*/
#if !defined(AFX_SYMTABLE_H__F8B4AD7F_07F9_4AB2_B206_04549837C7ED__INCLUDED_)
#define AFX_SYMTABLE_H__F8B4AD7F_07F9_4AB2_B206_04549837C7ED__INCLUDED_

class CSymTable
{
public:
    static int FindSymbol( const char* str, int* nchars );
};

#endif // !defined(AFX_SYMTABLE_H__F8B4AD7F_07F9_4AB2_B206_04549837C7ED__INCLUDED_)
