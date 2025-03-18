//-----------------------------------------------------------------------------
//  (c) 2004 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Fritz Dierks
//  $Header$
//-----------------------------------------------------------------------------
/*!
\file   IDestroy.h
\brief  Definition of interface IDestroy
*/

#ifndef GENAPI_IDESTROY_H
#define GENAPI_IDESTROY_H

#include <GenApi/GenApiDll.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // IDestroy interface
    //*************************************************************
    /**
    * \ingroup internal_itf
    * \brief Interface to destroy an object
    */

    interface GENAPI_DECL_ABSTRACT IDestroy
    {
        //! Makes the object to destro itself
        virtual void Destroy() = 0;

    };

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // GENAPI_IDESTROY_H
