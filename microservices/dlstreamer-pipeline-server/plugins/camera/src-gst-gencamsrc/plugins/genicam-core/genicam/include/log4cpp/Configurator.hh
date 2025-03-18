/*
 * Configurator.hh
 *
 * Copyright 2001, Glen Scott. All rights reserved.
 *
 * See the COPYING file for the terms of usage and distribution.
 */
#ifndef _LOG4CPP_CONFIGURATOR_HH
#define _LOG4CPP_CONFIGURATOR_HH

#ifdef _MSC_VER
#   pragma warning( disable: 4275 ) // non dll-interface structXXX used as base
#endif

#include <log4cpp/Portability.hh>
#include <log4cpp/Export.hh>
#include <string>
#include <stdexcept>

LOG4CPP_NS_BEGIN

/**
 * Exception class for configuration.
 */
class LOG4CPP_EXPORT ConfigureFailure : public std::runtime_error {
public:
    /**
     * Constructor.
     * @param reason String containing the description of the exception.
     */
    ConfigureFailure(const std::string& reason);
};

LOG4CPP_NS_END


#endif // _LOG4CPP_CONFIGURATOR_HH
