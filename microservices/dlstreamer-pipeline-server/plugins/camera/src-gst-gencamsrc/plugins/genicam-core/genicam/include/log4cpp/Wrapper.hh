#ifndef _LOG4CPP_WRAPPER_HH
#define _LOG4CPP_WRAPPER_HH

#include <log4cpp/Category.hh>
#include <log4cpp/NDC.hh>
#include <log4cpp/PatternLayout.hh>
#include <log4cpp/PropertyConfigurator.hh>
#if defined (_WIN32)
#include <log4cpp/Win32DebugAppender.hh>
#endif

LOG4CPP_NS_BEGIN
//! A function table which is bound to log4cpp's Category class
typedef struct {
    Category& (*getInstance)(const std::string& name);
    std::vector<Category*>* (*getCurrentCategories)();
    Category* (*exists)(const std::string& name);
    Category& (*getRoot)();
    void(*shutdown)();
    void (Category::*logva)(Priority::Value priority, const char* stringFormat, va_list va);
    bool (Category::*isInfoEnabled)();
    bool (Category::*isWarnEnabled)();
    bool (Category::*isDebugEnabled)();
    void (Category::*setPriority)(Priority::Value priority);
    void (Category::*addAppender)(Appender* appender);
    void (Category::*removeAppender)(Appender* appender);
} category_t;

//! A function table which is bound to log4cpp's PatternLayout class
typedef struct {
    PatternLayout* (*create)();
    void (PatternLayout::*setConversionPattern)(const std::string& conversionPattern);
    void(*destroy)(PatternLayout* object);
} pattern_layout_t;

//! A function table which is bound to log4cpp's PropertyConfigurator class
typedef struct {
    void(*configure)(std::istream& initStream);
} property_configurator_t;

//! A function table which is bound to log4cpp's NDC class
typedef struct {
    void(*push)(const std::string& message);
    std::string(*pop)();
} ndc_t;

#if defined (_WIN32)
//! A function table which is bound to log4cpp's Win32DebugAppender class
typedef struct {
    Appender *(*create)(const std::string& name);
} win32_debug_appender_t;
#endif

//! A function table which is bound to log4cpp's Appender class
typedef struct {
    Appender *(*createFileAppender)(const std::string& name, const std::string& fileName, bool append, mode_t mode);
    void (Appender::*setThreshold)(Priority::Value threshold);
    void (Appender::*setLayout)(Layout* layout);
} appender_t;

//! A wrapper which bridges to log4cpp functionality.
typedef struct {
    category_t Category;
    pattern_layout_t PatternLayout;
    property_configurator_t PropertyConfigurator;
    ndc_t NDC;
#if defined (_WIN32)
    win32_debug_appender_t Win32DebugAppender;
#endif
    appender_t Appender;
} wrapper_t;

//! A functionality wrapper (= a set of function tables) which is exported.
extern "C" LOG4CPP_EXPORT const LOG4CPP_NS::wrapper_t Wrapper;
LOG4CPP_NS_END

#endif // _LOG4CPP_WRAPPER_HH
