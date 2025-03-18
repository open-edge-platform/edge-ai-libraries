//-----------------------------------------------------------------------------
//  (c) 2005 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenICam
//  Author:  Fritz Dierks
//  $Header$
//-----------------------------------------------------------------------------
/*!
\file
\brief    helper functions
*/

#ifndef _LOG4CPP_UTILITIES_H
#define _LOG4CPP_UTILITIES_H

#include <string>
#if defined (_MSC_VER)
#include <Windows.h>
#endif

#if defined(UNDER_RTSS)
#include "RTSSUtilities.h"
#endif // defined(UNDER_RTSS)
#include <log4cpp/Portability.hh>

LOG4CPP_NS_BEGIN

// replaces entries of type $(VARIABLE) by the corresponding environment variable's content
bool ReplaceEnvironmentVariables(std::string &Buffer);

LOG4CPP_NS_END

#endif // _LOG4CPP_UTILITIES_H
