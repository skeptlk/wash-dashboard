fleetsummary_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("fleetsummary_workspace"))
  
}

fleetsummary_workspaceMod <- function(input, output, session, credentials, pool, id_tab) {
  
  ns <- session$ns
  
  # output$fleetsummary_table <- renderReactable({
  #   
  #   fleetsummary <- pool %>%
  #     tbl(in_schema("ecmapp", "_fleetsummary")) %>%
  #     # filter(
  #     #   operator == "utair"
  #     # ) %>%
  #     collect()
  #   
  #   fleetsummary <- fleetsummary[,c(
  #     "operator",
  #     "aircraft_family",
  #     "ac_reg_new",
  #     "ac_reg_old",
  #     "aircraft_id",
  #     "engine_position",
  #     "engine_id",
  #     "engine_family",
  #     "install_datetime",
  #     "removal_datetime"
  #     # "hrs_at_install",
  #     # "cyc_at_install",
  #     # "hrs_at_removal",
  #     # "cyc_at_removal",
  #     # "number_removals",
  #     # "number_shop_visits",
  #     # "deletion_flag",
  #     # "reason_for_removal",
  #     # "n1_modifier" 
  #   )]
  #   
  #   reactable(
  #     fleetsummary,
  #     searchable = TRUE,
  #     filterable = TRUE,
  #     showPageInfo = TRUE,
  #     showPagination = TRUE,
  #     
  #     wrap = FALSE,
  #     resizable = TRUE,
  #     striped = TRUE, 
  #     highlight = TRUE,
  #     
  #     groupBy = c(
  #       "operator",
  #       "aircraft_family",
  #       "ac_reg_new"
  #     ),
  #     bordered = TRUE
  #   )
  #   
  # })
  
  output$fleetsummary_table <- DT::renderDataTable(server = FALSE,{
    
    fleetsummary <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      # filter(
      #   operator == "utair"
      # ) %>%
      collect()
    
    engine_config <- pool %>%
      tbl(in_schema("ecmapp", "_engine_config")) %>%
      collect()
    
    
    engine_config <- engine_config %>% 
      group_by(engine_id) %>% 
      slice_max(change_date)
    
    engine_config <- engine_config[!duplicated(engine_config$engine_id),c("engine_id","n1_modifier")]
    
    fleetsummary <- fleetsummary %>%
      left_join(
        engine_config,
        by = c(
          "engine_id" = "engine_id"
        )
      )
    
    fleetsummary <- fleetsummary[,c(
      "operator",
      "aircraft_family",
      "ac_reg_new",
      "ac_reg_old",
      "aircraft_id",
      "engine_position",
      "engine_id",
      "engine_family",
      "install_datetime",
      "removal_datetime",
      "n1_modifier"
    )]
    
    DT::datatable({
      fleetsummary
    },
    caption = "History of install/remove",
    extensions = 'Buttons',
    
    options = list(
      dom = 'Bfrtip',
      
      buttons = list(
        list(
          extend = 'collection',  #'csv',
          buttons = c('csv', 'excel'),
          exportOptions = list(
            modifiers = list(page = "all")
          )
        )
      ),
      columnDefs=list(list(className='dt-center',targets="_all")
      ),
      scrollX = TRUE
    ),
    filter = "top",
    selection = 'single',
    # style = 'bootstrap',
    class = 'hover', 
    # class = 'cell-border stripe',
    rownames = FALSE
    )
    
  })
  
  output$onwing_table <- DT::renderDataTable(server = FALSE,{
    
    fleetsummary <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      collect()
    
    fleetsummary <- fleetsummary[!duplicated(
      fleetsummary[,c(
        "engine_id", 
        "install_datetime", 
        "removal_datetime", 
        "aircraft_id"
      )]),]
    
    fleetsummary_gr <- fleetsummary %>% 
      group_by(
        engine_id
      ) %>%
      summarise(
        last_install_datetime = max(install_datetime)
      ) %>%
      left_join(
        fleetsummary[,c(
          "operator",
          "engine_id",
          "install_datetime",
          "removal_datetime",
          "ac_reg_new",
          "ac_reg_old",
          "aircraft_id",
          "aircraft_grp"
        )],
        by = c(
          "engine_id" = "engine_id",
          "last_install_datetime" = "install_datetime"
        )
      )
    
    fleetsummary_gr$onwing_status <- "ONWING"
    
    fleetsummary_gr$onwing_status[!is.na(fleetsummary_gr$removal_datetime)] <- "SPARE"
    
    DT::datatable({
      fleetsummary_gr
    },
    caption = "Onwing table",
    extensions = 'Buttons',
    
    options = list(
      dom = 'Bfrtip',
      
      buttons = list(
        list(
          extend = 'collection',  #'csv',
          buttons = c('csv', 'excel'),
          exportOptions = list(
            modifiers = list(page = "all")
          )
        )
      ),
      columnDefs=list(list(className='dt-center',targets="_all")
      ),
      scrollX = TRUE
    ),
    filter = "top",
    selection = 'single',
    # style = 'bootstrap',
    class = 'hover', 
    # class = 'cell-border stripe',
    rownames = FALSE
    )
    
  })
  
  output$engineconfig_table <- DT::renderDataTable(server = FALSE,{
    
    engine_config <- pool %>%
      tbl(in_schema("ecmapp", "_engine_config")) %>%
      collect()
    # browser()
    fleetsummary <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      collect()
    
    fleetsummary <- fleetsummary[,c("engine_id","operator")]
    
    fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
    
    engine_config <- engine_config %>%
      left_join(
        fleetsummary,
        by = c("engine_id" = "engine_id")
      )
    
    DT::datatable({
      engine_config
    },
    caption = "Engine config",
    extensions = 'Buttons',
    
    options = list(
      dom = 'Bfrtip',
      
      buttons = list(
        list(
          extend = 'collection',  #'csv',
          buttons = c('csv', 'excel'),
          exportOptions = list(
            modifiers = list(page = "all")
          )
        )
      ),
      columnDefs=list(list(className='dt-center',targets="_all")
      ),
      scrollX = TRUE
    ),
    filter = "top",
    selection = 'single',
    # style = 'bootstrap',
    class = 'hover', 
    # class = 'cell-border stripe',
    rownames = FALSE
    )
    
  })
  
  output$fleetsummary_workspace <- renderUI({
    
    fluidRow(
      bs4TabCard(
        width = 12,
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "Fleet summary",
          #withSpinner(reactableOutput(ns("fleetsummary_table")))
          withSpinner(DT::dataTableOutput(ns("fleetsummary_table"))),
          withSpinner(DT::dataTableOutput(ns("onwing_table"))),
          withSpinner(DT::dataTableOutput(ns("engineconfig_table")))
        )
      )  
    )
    
  })
  
}