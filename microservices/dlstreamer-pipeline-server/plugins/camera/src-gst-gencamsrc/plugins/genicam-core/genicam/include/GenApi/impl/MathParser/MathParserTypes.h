#pragma once

#ifndef MATH_PARSER_TYPES_H_INCLUDED_
#define MATH_PARSER_TYPES_H_INCLUDED_

//Error messages

static const char
    eBrackets [] = "#Brackets do not match!",
    eSyntax   [] = "#Syntax error!",
    eInternal [] = "#Internal error!",
    eExtraOp  [] = "#Extra operation!",
    eInfinity [] = "#Infinity somewhere!",
    eInvArg   [] = "#Invalid argument!",
    eUnknFunc [] = "# %.*s - Unknown function/variable!", // if you change the format string, you must check also the sprintf below
    eExtrnFunc[] = "#External function error!",
    eLogicErr [] = "#Logical expression error!",
    eCalcErr  [] = "#Calculation error!",
    eUnexpEnd [] = "#Unexpected end of script!",
    eExpVarRet[] = "#Variable name or return expected!",
    eExpAssign[] = "#Assignment expected!",
    eValSizErr[] = "#Value too big for operation!",
    eInvPrmCnt[] = "#Invalid parameters count for function call!",
    eInvForm[]   = "#Invalid formula";

#endif // MATH_PARSER_TYPES_H_INCLUDED_
