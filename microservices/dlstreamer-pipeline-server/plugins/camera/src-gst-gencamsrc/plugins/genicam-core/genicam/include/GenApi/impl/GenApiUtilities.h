//-----------------------------------------------------------------------------
//  (c) 2005 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenICam
//  Author:  Fritz Dierks
//  $Header$
//-----------------------------------------------------------------------------
/*!
\file     GenApiUtilities.h
\brief    GenICam common utilities
*/

#ifndef GENAPI_GENAPIUTILITIES_DEF_H_
#define GENAPI_GENAPIUTILITIES_DEF_H_

#include <string>
#include "Base/GCString.h"

namespace GENAPI_NAMESPACE
{

  void ReplaceEnvironmentVariables(GENICAM_NAMESPACE::gcstring &Buffer);

}

#endif // GENAPI_GENAPIUTILITIES_DEF_H_
