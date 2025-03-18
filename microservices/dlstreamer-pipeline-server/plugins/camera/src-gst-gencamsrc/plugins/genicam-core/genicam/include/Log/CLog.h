//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section:  Vision Components
//  Project:  GenApi
//    Author:  Fritz Dierks
//  $Header$
//
//  License: This file is published under the license of the EMVA GenICam  Standard Group.
//  A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
//  If for some reason you are missing  this file please contact the EMVA or visit the website
//  (http://www.genicam.org) for a full copy.
//
//  THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
//  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
//  OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
//  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
//  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
//  ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
//  POSSIBILITY OF SUCH DAMAGE.
//-----------------------------------------------------------------------------
/**
\file
\brief    Implementation of CLog.
\ingroup Log_PublicUtilities
*/

#ifndef LOG_CLOG_H_
#define LOG_CLOG_H_

#ifdef _MSC_VER
#   pragma warning (push, 3)
#   pragma warning(disable:4706)  // assignment within conditional expression
#endif

#include <log4cpp/Portability.hh>
#include <log4cpp/Priority.hh>

namespace LOG4CPP_NS
{
    class Category;
    class Appender;
}

#include <stdio.h>
#include <Base/GCBase.h>
#include <Log/LogDll.h>

namespace GENICAM_NAMESPACE
{

    /**
    \brief Helper class encapsulating log4cpp
    \ingroup Log_PublicUtilities
    */
    class LOG_DECL CLog
    {
    public:

        //! Retrieves the root category
        static LOG4CPP_NS::Category& GetRootLogger( void );

        //! Retrieves (and if necessary create) a category by name
        static LOG4CPP_NS::Category& GetLogger( const gcstring &LoggerName );
        static LOG4CPP_NS::Category& GetLogger( const char LoggerName[] );

        //! Checks if a category exists
        static bool Exists( const gcstring &LoggerName );
        static bool Exists( const char LoggerName[] );

        //! Push nested diagnostic context
        static void PushNDC( const gcstring &ContextName );
        static void PushNDC( const char ContextName[] );

        //! Pop nested diagnostic context
        static void PopNDC( void );

        //! initializes log4cpp
        static void Initialize( void );

        //! de-initializes log4cpp
        static void ShutDown( void );

        //! Configures log4cpp to output messages >=ERROR on the Windows debug console
        static void ConfigureDefault();

        //! Configures log4cpp from a file
        static bool ConfigureFromFile( const gcstring &FileName );
        static bool ConfigureFromFile( const char FileName[] );

        //! Configures log4cpp from a file whose name is given by the environment variable GENICAM_LOG_CONFIG_VERSION
        static bool ConfigureFromEnvironment( void );

        //! Configures log4cpp from a string
        static bool ConfigureFromString( const gcstring &ConfigData );
        static bool ConfigureFromString( const char ConfigData[] );

        //! removes all appenders from all existing categories
        static void RemoveAllAppenders(void);

        //! Creates a new file appender (used by some test modules)
        static LOG4CPP_NS::Appender *CreateFileAppender( const gcstring &aName, const gcstring &aPath, bool aAppend = false, const gcstring &aPattern = "" );

        //! Add/remove an appender to/from a category
        static void AddAppender( LOG4CPP_NS::Category *aCategory, LOG4CPP_NS::Appender *aAppender );

        static void RemoveAppender( LOG4CPP_NS::Category *aCategory, LOG4CPP_NS::Appender *aAppender );


        //! Set priority for a category
        static void SetPriorityInfo( LOG4CPP_NS::Category *aCategory );
        static void SetPriorityError( LOG4CPP_NS::Category *aCategory );

        //! Check whether logging is possible and enabled for a specific category
        static bool IsInfoEnabled( LOG4CPP_NS::Category *aCategory );
        static bool IsWarnEnabled( LOG4CPP_NS::Category *aCategory );
        static bool IsDebugEnabled( LOG4CPP_NS::Category *aCategory );

        //! Logging functions
        static void LogPush( LOG4CPP_NS::Category *aCategory, LOG4CPP_NS::Priority::Value aPriority, const char *aStringFormat, ... );
        static void LogPop( LOG4CPP_NS::Category *aCategory, LOG4CPP_NS::Priority::Value aPriority, const char *aStringFormat, ... );
        static void Log( LOG4CPP_NS::Category *aCategory, LOG4CPP_NS::Priority::Value aPriority, const char *aStringFormat, ... );
        static void LogVA( LOG4CPP_NS::Category *aCategory, LOG4CPP_NS::Priority::Value aPriority, const char *aStringFormat, va_list arg );

    private:
        //! Makes sure log4cpp has been found.
        static void MakeSureLoggerHasBeenFound( void );

        //! Reference counter for Initialize/Shutdown
        static int g_RefCount;
        
        //! A wrapper which bridges log4cpp and this class.
        static const void *g_pLog4cpp;

        //! A type corresponds to a library handle which can be platform specific.
#if defined (_WIN32)
        typedef  HMODULE lib_handle_t;
#else
        typedef void * lib_handle_t;
#endif
        
        //! A handle to an associated logger library.
        static lib_handle_t g_pLibHandle;

        //! Opens a library.
        static lib_handle_t OpenLibrary( const gcstring Name );

        //! Finds a symbol and return its pointer.
        static void *FindSymbol( lib_handle_t Handle, const gcstring Name );
        
        //! A truth value of a proposition "Has found log4cpp."
        static bool g_HasFoundLogger;

    };

}

// Logging macros (can be replaced by real functions for compilers not supporting it?)
#define GCLOGINFO( cat, ... ) if(GENICAM_NAMESPACE::CLog::Exists("")) { GENICAM_NAMESPACE::CLog::Log( cat, LOG4CPP_NS::Priority::INFO, ##__VA_ARGS__ ); }
#define GCLOGINFOPUSH( cat, ... ) if(GENICAM_NAMESPACE::CLog::Exists("")) { GENICAM_NAMESPACE::CLog::LogPush( cat, LOG4CPP_NS::Priority::INFO, ##__VA_ARGS__ ); }
#define GCLOGINFOPOP( cat, ... ) if(GENICAM_NAMESPACE::CLog::Exists("")) { GENICAM_NAMESPACE::CLog::LogPop( cat, LOG4CPP_NS::Priority::INFO, ##__VA_ARGS__ ); }
#define GCLOGWARN( cat, ... ) if(GENICAM_NAMESPACE::CLog::Exists("")) { GENICAM_NAMESPACE::CLog::Log( cat, LOG4CPP_NS::Priority::WARN, ##__VA_ARGS__ ); }
#define GCLOGERROR( cat, ... ) if(GENICAM_NAMESPACE::CLog::Exists("")) { GENICAM_NAMESPACE::CLog::Log( cat, LOG4CPP_NS::Priority::ERROR, ##__VA_ARGS__ ); }
#define GCLOGDEBUG( cat, ... ) if(GENICAM_NAMESPACE::CLog::Exists("")) { GENICAM_NAMESPACE::CLog::Log( cat, LOG4CPP_NS::Priority::DEBUG,  ##__VA_ARGS__ ); }

#endif // LOG_CLOG_H_
