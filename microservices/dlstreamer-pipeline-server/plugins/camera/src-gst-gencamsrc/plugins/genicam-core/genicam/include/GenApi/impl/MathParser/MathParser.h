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
\brief    Definition of CMathParser


*/
#ifndef _MATHPARSER_H_
#define _MATHPARSER_H_

#include "MathParserDll.h"
#include "GenApi/Types.h"
#include "GenApi/GenApiDll.h"
#include "StrMap.h"
#include "Lexer.h"

#include <vector>

#ifdef _MSC_VER // *JS*
#   pragma warning(push)
#   pragma warning(disable: 4251) // class 'xxx' needs to have dll-interface to be used by clients of class 'yyy'
#endif

#define ORIGINAL_STACK_SIZE 64

extern const double DblErR;
extern const double DblNiN;


typedef double ( *OneArgFunc ) ( double arg );
typedef char* ( *MultiArgFunc ) ( int paramcnt, double* args,
                                  CStrMap* strparams, double* result );
typedef int ( *PrmSrchFunc ) ( const char* str, size_t len, double* value,
                               void* param );
/**
* \ingroup internal_impl
*
* \brief Expression parser and evaluator of CSwissKnife
*/
class MATHPARSERDLL_API CMathParser
{
    typedef enum
    {
        // Binary
        OP_SHL, OP_SHR, OP_POW,
        OP_LOGIC_NEQ, OP_LOGIC_GEQ, OP_LOGIC_LEQ,
        OP_LOGIC_AND, OP_LOGIC_OR, // Logical
        OP_COMSTART, OP_ASSIGN, // For internal needs
        OP_OBR, // Special
        OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD, OP_UNK, // Arithmetic
        OP_XOR, OP_NOT, OP_AND, OP_OR, // Bitwise
        OP_EQU, OP_GREATER, OP_LESS,
        OP_LOGIC, OP_LOGIC_SEP, OP_CBR, OP_COMMA, // Logical
        OP_FORMULAEND, // For script
        OP_INDEX_TO_VAR, OP_FUNC_ONEARG, OP_FUNC_MULTIARG // Special
    } OperType_t;
    static const signed char OpPriorities[OP_FUNC_MULTIARG + 1];
    typedef struct Operation
    {
        OperType_t  OperType;
        const void* Func;
        signed char PrevValTop;
        CStrMap*    StrParams;
        explicit Operation() : Func( 0 ), PrevValTop( 0 ), StrParams( 0 ) {}
        explicit Operation( OperType_t op ) : OperType( op ), Func( 0 ), PrevValTop( 0 ), StrParams( 0 ) {}
        explicit Operation( OperType_t op, const void* p, signed char a, CStrMap* pM ) : OperType( op ), Func( p ), PrevValTop( a ), StrParams( pM ) {}
    } Operation;
    static const Operation BrOp;
    static const Operation CbrOp;
    static const Operation NegOp;
    static const Operation ItvOp;
    static const Operation CommaOp;
    std::vector<Operation> OpStack;
    std::vector<Operation> OpStackEval;
    std::vector<double> ValStack;
    std::vector<double> ValStackEval;
    int    OpTop, ValTop;
    int    ObrDist;
    CLexer Lexer;
    CStrMap* VarParams;
    std::vector<char> errbuf;
    static CStaticFuncMapDouble DoubleFunctions;
    static CSymTable MathSymTable;
    const char* ParseFormula( bool ConvertUpperCase );
    const char* PrepareFormula();
    const char* Calc();
    const char* CalcToObr();
public:
    CStrMap* Parameters;
    CStrMap* ExtFunctions;
    PrmSrchFunc MoreParams;
    void*  ParamFuncParam;
    CMathParser( void );
    const char* Parse( const char* Formula, bool ConvertUpperCase );
    const char* Eval( double* result );
    ~CMathParser();
};

#ifdef _MSC_VER // *JS*
#   pragma warning(pop)
#endif

#endif //_MATHPARSER_H_
