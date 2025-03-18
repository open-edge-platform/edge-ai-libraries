/*
 * BasicConfigurator.hh
 *
 * Copyright 2002, Log4cpp Project. All rights reserved.
 *
 * See the COPYING file for the terms of usage and distribution.
 */
#ifndef _LOG4CPP_BASICCONFIGURATOR_HH
#define _LOG4CPP_BASICCONFIGURATOR_HH

#include <log4cpp/Portability.hh>

LOG4CPP_NS_BEGIN

/**
   This class implements a trivial default configuration for log4cpp:
   it adds a FileAppender that logs to stdout and uses a BasicLayout to
   the root Category.
   @since 0.3.2
   **/
class LOG4CPP_EXPORT BasicConfigurator {
public:

    /**
       Performs a minimal configuration of log4cpp.
       **/
    static void configure();
};

LOG4CPP_NS_END

#endif
