//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Margret Albrecht
//  $Header$
//
// License: Derived from Kirill Zaborski's MathParser library (http://kirya.narod.ru/mathparser.html ).
// This library comes under LGPL license (see http://www.gnu.org/licenses/lgpl.html).
// Kirill's implementation is a C++ port of the CCalc library from Walery Studennikov (http://www.sama.ru/~despair/ccalc/)
// which also comes under the LGPL.
//-----------------------------------------------------------------------------
/*!
\file
\brief    Export Macros
*/

// The following ifdef block is the standard way of creating macros which make exporting
// from a DLL simpler. All files within this DLL are compiled with the MATHPARSERDLL_EXPORTS
// symbol defined on the command line. this symbol should not be defined on any project
// that uses this DLL. This way any other project whose source files include this file see
// MATHPARSERDLL_API functions as being imported from a DLL, whereas this DLL sees symbols
// defined with this macro as being exported.

#if defined (_MSC_VER)

#if defined(UNDER_RTSS)
#include "RTmalloc\RTmalloc.h"
#endif

#ifdef MATHPARSERDLL_EXPORTS
#   define MATHPARSERDLL_API __declspec(dllexport)
#else
#   define MATHPARSERDLL_API __declspec(dllimport)
#endif

#elif defined (__GNUC__) && (defined (__linux__) || defined(__APPLE__) || defined(VXWORKS))

#ifdef MATHPARSERDLL_EXPORTS
#   define MATHPARSERDLL_API __attribute__((visibility("default")))
#else
#   define MATHPARSERDLL_API
#endif

#else
#   define MATHPARSERDLL_API
#endif
