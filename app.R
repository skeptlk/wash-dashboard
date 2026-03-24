library(DT)
library(shiny)
library(bs4Dash)
library(shinymanager)
library(shinyjs)
library(dbplyr)
library(dplyr)
library(DBI)
library(pool)
library(RPostgreSQL)
library(ini)
library(shinyWidgets)
library(shinycssloaders)
library(highcharter)
library(data.table)
library(shinyscreenshot)
library(xts)
library(reactable)
library(sortable)
library(tidyr)

for(lf in list.files('./modules/',full.names = T, recursive = T)){
  source(lf)
}

for(lf in list.files('./utils/',full.names = T, recursive = T)){
  source(lf)
}

config_list <- read.ini(
  './config/config.ini',
  encoding = getOption("encoding")
)

pool <- dbPool(
  drv = dbDriver("PostgreSQL"),
  dbname = config_list$PROJECT_DB_ECM_NEW$dbname,
  host =  config_list$PROJECT_DB_ECM_NEW$host,
  port = config_list$PROJECT_DB_ECM_NEW$port,
  user = config_list$PROJECT_DB_ECM_NEW$user,
  password = config_list$PROJECT_DB_ECM_NEW$psw
)

onStop(function() {
  poolClose(pool)
})

#userbase <- pool %>% tbl(in_schema("ecmapp", "userbase")) %>% collect()

credentials <- data.frame(
  #user = userbase$user,
  user = c(
    "user1",
    "PadaletsNV",
    "i.merzlikin@s7.ru",
    "r.kozyrev@s7.ru",
    "n.bobov@s7.ru",
    "v.susanin@s7.ru",
    "v.plotnikov@s7.ru",
    "d.y.shmanatov@s7.ru",
    "n.skovpen@s7.ru",
    "i.s.skorokhodov@s7.ru",
    "d.v.smirnov@s7.ru",
    "v.n.ulezko@s7.ru",
    "o.kireev@s7.ru",
    "r.kireev@s7.ru",
    "mrbrown"
    # ,"natalya.batischeva@utair.ru",
    # "ivan.d.gusev@utair.ru",
    # "Grigoriy.Zyryanov@utair.ru",
    # "viktor.mishutkin@utair.ru",
    # "Ildar.Nigmatullin@utair.ru",
    # "anton.platonov@utair.ru",
    # "Roman.Filipchenko@utair.ru",
    # "albert.salimov@utair.ru"
  ),
  password = c( 
    "pass1",
    "^-72P{RxK",
    "[LU'd6T,^",
    ";gU4gm@8S",
    "mhV_(*_5A",
    "+U=rJ;f83",
    "^-72P{RxK",
    "Rm5tA6_Ed",
    "8S2vY_qK7",
    ".3t[qHm<(",
    ",:Z.f9@;z",
    "mhV_(*_5A",
    "3}A2_ZXn4",
    "WCXX4<t@B",
    ".3t[qHm<("
    # ,"^-72P{RxK",
    # "[LU'd6T,^",
    # ";gU4gm@8S",
    # "mhV_(*_5A",
    # "+U=rJ;f83",
    # "^-72P{RxK",
    # "+-12DsmKL",
    # "[LU'd6T,^"
  ),
  # password = rep("pass1", nrow(userbase)),
  # is_hashed_password = TRUE,
  stringsAsFactors = FALSE
)

userbase <- credentials

ui <- secure_app(
  tags_top =
    tags$div(
      tags$img(
        src = 'https://www.s7.ru/images/icons/icon-600x400.jpg',
        width = 100
      ),
      tags$h4("Engine Condition Monitoring", style = "align:center")
    ),
  # add information on bottom ?
  tags_bottom = tags$div(
    tags$p(
      "For any question, please contact ",
      tags$a(
        href = "mailto:v.azanov@s7.ru?Subject=EngineConditionMonitoring%20S7",
        target="_top", "v.azanov@s7.ru"
      ),
      " or ",
      tags$a(
        href = "mailto:d.y.shmanatov@s7.ru?Subject=EngineConditionMonitoring%20S7",
        target="_top", "d.y.shmanatov@s7.ru"
      )
    )
  ),
  fab_position = "bottom-left",
  background = "url('https://img2.goodfon.ru/original/2880x1800/c/f4/art-turbovintovoy-dvigatel.jpg');",
  bs4DashPage(
    title = "ECM",
    fullscreen = TRUE,
    scrollToTop = TRUE,
    header = bs4DashNavbar(
      #title = "shinyauthr",
      title = bs4DashBrand(
        title = "ECM",
        color = "primary",
        href = "https://www.s7.ru",
        image = "https://www.s7.ru/images/icons/icon-600x400.jpg"
      ),
      skin = "light",
      status = "white",
      border = TRUE,
      sidebarIcon = icon("bars"),
      controlbarIcon = icon("th")
      #compact = TRUE,
      #fixed = TRUE
      #,headerModUI("id_engine_trends_header")
    ),
    
    sidebar = bs4DashSidebar(
      collapsed = TRUE,
      bs4SidebarMenu(
        id = "tabs",
        bs4SidebarMenuItem(
          "Engine Trends",
          icon = icon('fighter-jet'),
          tabName = "engine_trends"
        ),
        
        bs4SidebarMenuItem(
          "Fleet Reports",
          icon = icon("stats",lib='glyphicon'),
          tabName = "fleet_reports"
        ),
        
        # bs4SidebarMenuItem(
        #   "Alerts",
        #   icon = icon("warning-sign",lib='glyphicon'),
        #   tabName = "alerts"
        # ),
        
        bs4SidebarMenuItem(
          "Maintenance",
          icon = icon("wrench"),
          tabName = "maintenance"
        ),
        
        bs4SidebarMenuItem(
          "Fleet Summary",
          icon = icon("check"),
          tabName = "fleet_summary"
        ),
        bs4SidebarMenuItem(
          "Constructor",
          icon = icon("plus"),
          tabName = "constructor"
        ),
        bs4SidebarMenuItem(
          "Parameters",
          icon = icon("book"),
          tabName = "parameters"
        ),
        bs4SidebarMenuItem(
          "User Options",
          icon = icon("user"),
          tabName = "user_options"
        )
        ,bs4SidebarMenuItem(
          "Data Quality",
          icon = icon("database"),
          tabName = "data_quality"
        )
        ,bs4SidebarMenuItem(
          "Engine Wash",
          icon = icon("bath"),
          tabName = "engine_wash"
        )
      )
    ),
    controlbar = bs4DashControlbar(
      skin = "light",
      pinned = TRUE,
      collapsed = FALSE,
      overlay = FALSE
      ,controlbarModUI("enginetrends_controlbar")
    ),
    footer = bs4DashFooter(),
    body = bs4DashBody(
      bs4TabItems(
        bs4TabItem(
          tabName = "engine_trends",
          enginetrends_workspaceModUI("id_engine_trends")
        ),
        bs4TabItem(
          tabName = "fleet_reports",
          fleetreports_workspaceModUI("id_fleet_reports")
        ),
        # bs4TabItem( 
        #   tabName = "alerts",
        #   alerts_workspaceModUI("id_alerts")
        # ),
        bs4TabItem(
          tabName = "maintenance",
          maintenance_workspaceModUI("id_maintenance")
        ),
        bs4TabItem(
          tabName = "fleet_summary",
          fleetsummary_workspaceModUI("id_fleetsummary")
        ),
        bs4TabItem(
          tabName = "constructor",
          #uiOutput("constructor_tab")
          constructor_workspaceModUI("id_constructor")
        ),
        bs4TabItem(
          tabName = "parameters",
          parameters_workspaceModUI("id_parameters")
        ),
        bs4TabItem(
          tabName = "user_options",
          useroptions_workspaceModUI("id_useroptions")
        )
        ,bs4TabItem(
          tabName = "data_quality",
          dataquality_workspaceModUI("id_dataquality")
        )
        ,bs4TabItem(
          tabName = "engine_wash",
          enginewash_workspaceModUI("id_enginewash")
        )
      )
    )
  )
)

server <- function(input, output, session) {
  
  result_auth <- secure_server(check_credentials = check_credentials(credentials),timeout = 0)
  
  # headerselectors_config <- callModule(
  #   headerMod,
  #   "id_engine_trends_header",
  #   credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
  #   pool = pool,
  #   id_tab = reactive(input$tabs)
  # )
  
  callModule(
    controlbarMod,
    "enginetrends_controlbar",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    id_tab = reactive(input$tabs)
  )
  
  enginetrends_data <- callModule(
    enginetrends_workspaceMod,
    "id_engine_trends",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    #headerselectors = NULL,#headerselectors_config,
    pool = pool
    #id_tab = reactive(input$tabs)
  )
  
  fleetreports_data <- callModule(
    fleetreports_workspaceMod,
    "id_fleet_reports",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    pool = pool
  )
  
  # constructor_id_sorted <- callModule(
  #   constructor_controlbarMod,
  #   "constructor_parameters",
  #   credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
  #   headerselectors = headerselectors_config,
  #   pool = pool,
  #   id_tab = reactive(input$tabs)
  # )
  
  constructor_data <- callModule(
    constructor_workspaceMod,
    "id_constructor",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    #headerselectors = headerselectors_config,
    #constructor_id_sorted = constructor_id_sorted,
    pool = pool
    #,id_tab = reactive(input$tabs)
  )
  
  callModule(
    maintenance_workspaceMod,
    "id_maintenance",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    #headerselectors = headerselectors_config,
    pool = pool
    #id_tab = reactive(input$tabs)
  )
  
  
  # # callModule(
  # #   alerts_workspaceMod,
  # #   "id_alerts",
  # #   credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
  # #   headerselectors = headerselectors_config,
  # #   pool = pool,
  # #   id_tab = reactive(input$tabs)
  # # )
  # 
  callModule(
    fleetsummary_workspaceMod,
    "id_fleetsummary",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    pool = pool
    #id_tab = reactive(input$tabs)
  )
  
  callModule(
    parameters_workspaceMod,
    "id_parameters",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    pool = pool
  )
   
  callModule(
    dataquality_workspaceMod,
    "id_dataquality",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    #headerselectors = headerselectors_config,
    pool = pool
    #id_tab = reactive(input$tabs)
  )
  
  callModule(
    enginetrendsfleetconfigurationMod,
    "enginetrends_fleetconfiguration",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    #headerselectors = headerselectors_config,
    enginetrends_data = enginetrends_data,
    pool = pool,
    id_tab = reactive(input$tabs)
  )

  callModule(
    presetsummaryMod,
    "enginetrends_presetsummary",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    workspace_data = enginetrends_data,
    pool = pool,
    id_tab = reactive(input$tabs)
  )
  
  callModule(
    presetsummaryMod,
    "fleetreports_presetsummary",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    workspace_data = fleetreports_data,
    pool = pool,
    id_tab = reactive(input$tabs)
  )
  
  callModule(
    useroptions_workspaceMod,
    "id_useroptions",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    pool = pool
    # headerselectors = headerselectors_config,
    # id_tab = reactive(input$tabs)
  )
  
  callModule(
    enginewash_workspaceMod,
    "id_enginewash",
    credentials = reactive(userbase[userbase$user == reactiveValuesToList(result_auth)$user,]),
    #headerselectors = headerselectors_config,
    pool = pool
    #id_tab = reactive(input$tabs)
  )
  
  
}

shinyApp(ui, server)